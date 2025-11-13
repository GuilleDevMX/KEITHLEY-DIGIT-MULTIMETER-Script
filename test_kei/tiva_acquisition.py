"""
TIVA Data Acquisition Module

This module provides functionality for acquiring data from a TIVA microcontroller
via serial communication. It reads IEEE 754 float values encapsulated in a custom
protocol with start/end bytes and checksum validation.

Protocol format:
- Start byte: 170 (0xAA)
- Payload: 4 bytes (IEEE 754 float)
- Checksum: 1 byte (sum of payload bytes % 256)
- End byte: 65 (0x41)

The module saves data to CSV format and generates PWL files for SPICE simulation.

Author: GuilleDevMX
Date: November 2025
"""

import serial
import csv
import numpy as np
import time
import threading
import os

acquisition_running = False

def setup_serial_connections():
    global ser_tiva
    try:
        ser_tiva = serial.Serial('COM6', 115200, timeout=1)  # Changed to COM6 as in main code
        time.sleep(2)  # Allow time for connections to establish
        print("Serial connection established on COM6")
    except serial.SerialException as e:
        print(f"Error opening serial port COM6: {e}")
        print("Please check if the TIVA device is connected and the port is correct.")
        raise

def start_acquisition():
    global acquisition_running
    acquisition_running = True
    # Start the data acquisition process
    threading.Thread(target=acquire_data).start()

def test_tiva_connection(ser_tiva):
    """Test the TIVA connection by attempting to read data"""
    try:
        print("Testing TIVA connection...")
        result = [None]
        read_tiva(ser_tiva, result)
        if result[0] is not None:
            print(f"✅ TIVA connection successful. Sample value: {result[0]}")
            return True
        else:
            print("⚠️  TIVA connection established but no valid data received")
            return True  # Connection is OK, just no data yet
    except Exception as e:
        print(f"❌ TIVA connection test failed: {e}")
        return False

def read_tiva(ser_tiva, result):
    """Leer datos del TIVA de manera optimizada"""
    try:
        linea_raw = ser_tiva.readline()
        if not linea_raw or len(linea_raw) < 7:  # Expecting 7 bytes minimum
            result[:] = [None]
            return

        # Expected 7 bytes: start byte (170), 4 bytes payload (IEEE 754 float), checksum, end byte (65)
        start_byte = linea_raw[0]
        end_byte = linea_raw[-1]

        if start_byte != 170 or end_byte != 65:
            result[:] = [None]
            return

        payload = linea_raw[1:5]  # 4 bytes for float
        checksum = linea_raw[5]

        # Verify checksum (sum of payload bytes modulo 256)
        calculated_checksum = sum(payload) % 256
        if calculated_checksum != checksum:
            result[:] = [None]
            return

        # Convert payload to float
        value = np.frombuffer(payload, dtype=np.float32)[0]
        result[0] = f"{value:.6f}"

    except Exception as e:
        print(f"Error reading TIVA data: {e}")
        result[:] = [None]

def acquire_data():
    try:
        setup_serial_connections()

        # Test TIVA connection
        if not test_tiva_connection(ser_tiva):
            print("Aborting acquisition due to connection issues")
            return

        timestamp_start = time.strftime("%Y%m%d-%H%M%S")
        csv_filename = f'tiva_data_{timestamp_start}.csv'
        pwl_filename = f'tiva_pwl_{timestamp_start}.pwl'
        
        with open(csv_filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Sample Number', 'Time (s)', 'TIVA Raw'])
        
        start_time = time.time()
        sample_count = 0
        buffer = []
        pwl_data = []  # To store time and raw voltage for PWL
        raw_values = []  # To accumulate raw values for averaging

        while time.time() - start_time < 10:  # Acquire for 10 seconds
            result = [None]
            read_tiva(ser_tiva, result)
            current_time = time.time() - start_time  # Relative time in seconds
            sample_count += 1
            buffer.append([sample_count, f"{current_time:.4f}"] + result)

            # Accumulate values for averaging
            if result[0] is not None:
                raw_value = float(result[0])
                raw_values.append(raw_value)
                pwl_data.append((f"{current_time:.4f}", raw_value))  # Store as float
            else:
                pwl_data.append((f"{current_time:.4f}", 0.0))  # Default to 0.0 if no data
            
            # Save every 20 samples
            if len(buffer) >= 20:
                with open(csv_filename, mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerows(buffer)
                buffer = []  # Clear buffer
        
        # Save remaining samples in buffer
        if buffer:
            with open(csv_filename, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerows(buffer)

        # Calculate averages and append to CSV
        if raw_values:
            avg_raw = np.mean(raw_values)
            with open(csv_filename, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['Average', '', f"{avg_raw:.6f}"])
        else:
            avg_raw = 0.0

        # Calculate sampling rate
        end_time = time.time()
        total_time = end_time - start_time
        sampling_rate = sample_count / total_time if total_time > 0 else 0

        print(f'Acquisition completed. Total samples: {sample_count}')
        print(f'Total time: {total_time:.2f} seconds')
        print(f'Sampling rate: {sampling_rate:.2f} samples/second')
        print(f'Data saved to {csv_filename}')
        print(f'Average raw value: {avg_raw:.6f}')
        
        # Save PWL file for SPICE simulation
        if pwl_data:
            with open(pwl_filename, 'w') as pwl_file:
                pwl_file.write("* TIVA Data for SPICE PWL source\n")
                pwl_file.write("* Time Voltage\n")
                for time_val, voltage in pwl_data:
                    pwl_file.write(f"{time_val} {voltage}\n")
            print(f'PWL data saved to {pwl_filename}')
    except Exception as e:
        print(f"Error during acquisition: {e}")
    finally:
        if 'ser_tiva' in globals():
            ser_tiva.close()

if __name__ == "__main__":
    acquire_data()