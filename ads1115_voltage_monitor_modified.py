import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import queue
import time
from collections import deque
import sys
import csv
from datetime import datetime, timedelta
import os

class VoltageMonitorApp:
    def __init__(self, root):
        print("Initializing VoltageMonitorApp...")
        self.root = root
        self.root.title("ADS1115 Voltage Monitor")
        self.root.minsize(800, 600)
        
        # Temporarily disable icon loading to ensure program starts
        # try:
        #     icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        #     if os.path.exists(icon_path):
        #         icon = tk.PhotoImage(file=icon_path)
        #         self.root.iconphoto(True, icon)
        #         self.log("Icon loaded successfully.")
        #     else:
        #         self.log("Icon file 'icon.png' not found in the script directory. Using default icon.")
        # except tk.TclError as e:
        #     self.log(f"Failed to load icon: {e}. Using default icon.")
        
        # Serial port variables
        self.serial_port = None
        self.baud_rate = 115200
        self.running = False
        self.data_queue = queue.Queue()
        
        # CSV file handling
        self.csv_file = None
        self.csv_writer = None
        
        # Use real-time as the start time (current system time: 04:08 PM KST, May 24, 2025)
        self.start_time = datetime.now()
        self.current_time = self.start_time
        
        # Data storage for plotting
        self.max_points = 6000
        self.times = deque(maxlen=self.max_points)
        self.voltages = [deque(maxlen=self.max_points) for _ in range(4)]
        self.max_voltage = 0
        self.plot_start_time = time.time()
        
        # Time scale for x-axis (in seconds)
        self.time_scale = tk.StringVar(value="10s")
        self.time_scale_map = {
            '1s': 1, '10s': 10, '20s': 20,
            '1min': 60, '5min': 300, '10min': 600
        }
        
        # GUI elements
        self.setup_gui()
        
        # Setup plot
        self.setup_plot()
        
        # Start the data processing thread
        print("Starting process thread...")
        self.process_thread = threading.Thread(target=self.process_data, daemon=True)
        self.process_thread.start()
        
        # Start the plot update loop
        print("Starting update plot loop...")
        self.update_plot()
        
        # Log errors to console
        self.log = print
        
    def setup_gui(self):
        print("Setting up GUI...")
        self.root.grid_rowconfigure(3, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Port selection frame
        port_frame = ttk.LabelFrame(self.root, text="Serial Port Selection")
        port_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        port_frame.grid_columnconfigure(0, weight=1)
        
        # COM port dropdown
        self.port_var = tk.StringVar()
        self.port_dropdown = ttk.Combobox(port_frame, textvariable=self.port_var, state="readonly")
        self.refresh_ports()
        self.port_dropdown.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        # Baud rate dropdown
        self.baud_var = tk.StringVar(value=str(self.baud_rate))
        baud_rates = ['9600', '19200', '38400', '57600', '115200', '230400', '460800']
        self.baud_dropdown = ttk.Combobox(port_frame, textvariable=self.baud_var, values=baud_rates, state="readonly")
        self.baud_dropdown.grid(row=0, column=1, padx=5, pady=5)
        
        # Connect/Disconnect/Refresh buttons
        self.connect_btn = ttk.Button(port_frame, text="Connect", command=self.connect)
        self.connect_btn.grid(row=0, column=2, padx=5, pady=5)
        
        self.disconnect_btn = ttk.Button(port_frame, text="Disconnect", command=self.disconnect, state="disabled")
        self.disconnect_btn.grid(row=0, column=3, padx=5, pady=5)
        
        self.refresh_btn = ttk.Button(port_frame, text="Refresh Ports", command=self.refresh_ports)
        self.refresh_btn.grid(row=0, column=4, padx=5, pady=5)
        
        # Time scale and reset frame
        timescale_frame = ttk.LabelFrame(self.root, text="Time Scale")
        timescale_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        timescale_dropdown = ttk.Combobox(timescale_frame, textvariable=self.time_scale, 
                                        values=['1s', '10s', '20s', '1min', '5min', '10min'], state="readonly")
        timescale_dropdown.grid(row=0, column=0, padx=5, pady=5)
        
        self.reset_btn = ttk.Button(timescale_frame, text="Reset Graph", command=self.reset_graph)
        self.reset_btn.grid(row=0, column=1, padx=5, pady=5)
        
        # Voltage display frame
        voltage_frame = ttk.LabelFrame(self.root, text="Channel Voltages (0-100V)")
        voltage_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        
        # Labels for displaying voltages
        self.voltage_labels = []
        for i in range(4):
            label = ttk.Label(voltage_frame, text=f"Channel {i+1}: 0.000 V")
            label.grid(row=i//2, column=i%2, padx=10, pady=5)
            self.voltage_labels.append(label)
        
    def setup_plot(self):
        print("Setting up plot...")
        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        self.lines = []
        colors = ['b', 'g', 'r', 'c']
        for i in range(4):
            line, = self.ax.plot([], [], colors[i], label=f'Channel {i+1}')
            self.lines.append(line)
        
        self.ax.set_title("Real-Time Voltage (Auto-Scaled)")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Voltage (V)")
        self.ax.set_ylim(0, 10)
        self.ax.grid(True)
        self.ax.legend()
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().grid(row=3, column=0, padx=10, pady=10, sticky="nsew")
        self.canvas.get_tk_widget().grid_rowconfigure(0, weight=1)
        self.canvas.get_tk_widget().grid_columnconfigure(0, weight=1)
        
    def refresh_ports(self):
        print("Refreshing ports...")
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_dropdown['values'] = ports
        if ports:
            self.port_var.set(ports[0])
        else:
            self.port_var.set("")
            self.log("No serial ports found!")
            
    def connect(self):
        print("Connecting to port...")
        port = self.port_var.get()
        if not port:
            messagebox.showerror("Error", "Please select a port!")
            return
        
        try:
            self.baud_rate = int(self.baud_var.get())
            self.serial_port = serial.Serial(port, self.baud_rate, timeout=1)
            self.running = True
            self.connect_btn.config(state="disabled")
            self.disconnect_btn.config(state="normal")
            
            port_name = os.path.basename(port)
            start_time_str = self.start_time.strftime("%Y%m%d_%H%M%S")
            csv_filename = f"{port_name}_{start_time_str}.CSV"
            self.csv_file = open(csv_filename, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(["Timestamp", "Channel 1 (V)", "Channel 2 (V)", "Channel 3 (V)", "Channel 4 (V)"])
            self.log(f"Logging to {csv_filename}")
            
            self.read_thread = threading.Thread(target=self.read_serial, daemon=True)
            self.read_thread.start()
            self.log(f"Connected to {port} at {self.baud_rate} baud")
        except Exception as e:
            self.log(f"Failed to connect: {str(e)}")
            messagebox.showerror("Error", f"Failed to connect: {str(e)}")
            self.serial_port = None
            
    def disconnect(self):
        print("Disconnecting from port...")
        self.running = False
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.serial_port = None
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None
            self.log("CSV file closed")
        self.connect_btn.config(state="normal")
        self.disconnect_btn.config(state="disabled")
        self.log("Disconnected")
        
    def read_serial(self):
        print("Starting serial read thread...")
        while self.running and self.serial_port:
            try:
                if self.serial_port.in_waiting > 0:
                    line = self.serial_port.readline().decode('utf-8').strip()
                    if line:
                        self.data_queue.put(line)
            except Exception as e:
                self.log(f"Serial read error: {e}")
                self.disconnect()
                break
                
    def process_data(self):
        print("Starting data processing...")
        self.plot_start_time = time.time()
        while True:
            try:
                data = self.data_queue.get(timeout=0.1)
                if ',' in data:
                    values = data.split(',')
                    if len(values) == 4:
                        voltages = []
                        for i, val in enumerate(values):
                            try:
                                voltage = float(val.split(':')[1])
                                voltages.append(voltage)
                            except (IndexError, ValueError) as e:
                                self.log(f"Parsing error for {val}: {e}")
                                continue
                        
                        if len(voltages) == 4:
                            for i, voltage in enumerate(voltages):
                                self.voltage_labels[i].config(text=f"Channel {i+1}: {voltage:.3f} V")
                            
                            self.max_voltage = max(self.max_voltage, max(voltages))
                            
                            # Use real-time for plotting
                            current_time = time.time() - self.plot_start_time
                            self.times.append(current_time)
                            for i in range(4):
                                self.voltages[i].append(voltages[i])
                            
                            if self.csv_writer:
                                # Use real-time with millisecond precision
                                real_time = datetime.now()
                                timestamp = real_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Milliseconds only
                                self.csv_writer.writerow([timestamp] + voltages)
                                self.csv_file.flush()
            except queue.Empty:
                continue
            except Exception as e:
                self.log(f"Data processing error: {e}")
                
    def reset_graph(self):
        print("Resetting graph...")
        self.times.clear()
        for voltage in self.voltages:
            voltage.clear()
        self.max_voltage = 0
        self.plot_start_time = time.time()
        
        for line in self.lines:
            line.set_xdata([])
            line.set_ydata([])
        self.ax.set_ylim(0, 10)
        self.ax.set_xlim(0, self.time_scale_map[self.time_scale.get()])
        self.canvas.draw()
        self.log("Graph reset")
        
    def update_plot(self):
        print("Updating plot...")
        if self.times:
            times = list(self.times)
            time_range = self.time_scale_map[self.time_scale.get()]
            
            if times[-1] <= time_range:
                x_min = 0
                x_max = time_range
            else:
                x_min = times[-1] - time_range
                x_max = times[-1]
            
            for i in range(4):
                self.lines[i].set_xdata(times)
                self.lines[i].set_ydata(list(self.voltages[i]))
            
            y_max = max(10, self.max_voltage + 10)
            self.ax.set_ylim(0, y_max)
            self.ax.set_xlim(x_min, x_max)
            self.canvas.draw()
        
        self.root.after(100, self.update_plot)
        
    def on_closing(self):
        print("Closing application...")
        self.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    try:
        print("Starting main application...")
        root = tk.Tk()
        app = VoltageMonitorApp(root)
        root.protocol("WM_DELETE_WINDOW", app.on_closing)
        root.mainloop()
    except Exception as e:
        print(f"Application error: {e}", file=sys.stderr)