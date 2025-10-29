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

def stop_acquisition():
    global acquisition_running
    acquisition_running = False
    if 'ser_tiva' in globals():
        ser_tiva.close()

def read_tiva(ser_tiva, result):
    """Leer datos del TIVA de manera optimizada"""
    linea_raw = ser_tiva.readline().strip()
    if not linea_raw or len(linea_raw) < 12:
        result[:] = [None, None, None]
        return

    # Función auxiliar para parsear valores de 2 bytes
    def parse_value(high_byte, low_byte):
        alto = (high_byte >> 4) & 0x0F
        bajo = high_byte & 0x0F
        alto1 = (low_byte >> 4) & 0x0F
        bajo1 = low_byte & 0x0F
        return alto * 0.1 + bajo * 0.01 + alto1 * 0.001 + bajo1 * 0.0001

    def parse_tiva_data(linea_raw) -> list:
        """Función para parsear datos TIVA"""
        if linea_raw and len(linea_raw) >= 12:
            valor = linea_raw[1]
            ALTO = (valor >> 4) & 0x0F
            BAJO = valor & 0x0F
            valor1 = linea_raw[2]
            ALTO1 = (valor1 >> 4) & 0x0F
            BAJO1 = valor1 & 0x0F
            valor2 = linea_raw[3]
            ALTO2 = (valor2 >> 4) & 0x0F
            BAJO2 = valor2 & 0x0F
            tiva_raw = ALTO * 0.1 + BAJO * 0.01 + ALTO1 * 0.001 + BAJO1 * 0.0001 + ALTO2 * 0.00001 + BAJO2 * 0.000001

            valor = linea_raw[6]
            ALTO = (valor >> 4) & 0x0F
            BAJO = valor & 0x0F
            valor1 = linea_raw[7]
            ALTO1 = (valor1 >> 4) & 0x0F
            BAJO1 = valor1 & 0x0F
            valor2 = linea_raw[8]
            ALTO2 = (valor2 >> 4) & 0x0F
            BAJO2 = valor2 & 0x0F
            tiva_fir = ALTO * 0.1 + BAJO * 0.01 + ALTO1 * 0.001 + BAJO1 * 0.0001 + ALTO2 * 0.00001 + BAJO2 * 0.000001

            valor = linea_raw[10]
            TEMP_ALTO = (valor >> 4) & 0x0F
            TEMP_BAJO = valor & 0x0F
            valor1 = linea_raw[11]
            TEMP1_ALTO = (valor1 >> 4) & 0x0F
            TEMP1_BAJO = valor1 & 0x0F
            tiva_temp = TEMP_ALTO *10 + TEMP_BAJO  + TEMP1_ALTO * 0.1 + TEMP1_BAJO * 0.01

            if linea_raw[0] == 45:  # Si es negativo
                tiva_raw = tiva_raw * -1

            if linea_raw[5] == 45:  # Si es negativo
                tiva_fir = tiva_fir * -1

            res = [None, None, None]
            res[0] = tiva_raw
            res[1] = tiva_fir
            res[2] = tiva_temp

            return res

    tiva_data = parse_tiva_data(linea_raw)
    com_tiva_raw = tiva_data[0]
    com_tiva_filtrado = tiva_data[1]
    com_tiva_temp = tiva_data[2]
    
    result[:] = [
        com_tiva_raw,
        com_tiva_filtrado,
        com_tiva_temp
    ]

def acquire_data():
    try:
        setup_serial_connections()
        timestamp_start = time.strftime("%Y%m%d-%H%M%S")
        csv_filename = f'tiva_data_{timestamp_start}.csv'
        pwl_filename = f'tiva_pwl_{timestamp_start}.pwl'
        
        with open(csv_filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Sample Number', 'Time (s)', 'TIVA Raw', 'TIVA Filtered', 'TIVA Temp'])
        
        start_time = time.time()
        sample_count = 0
        buffer = []
        pwl_data = []  # To store time and raw voltage for PWL
        raw_values = []  # To accumulate raw values for averaging
        filtered_values = []  # To accumulate filtered values for averaging
        temp_values = []  # To accumulate temp values for averaging

        while time.time() - start_time < 10:  # Acquire for 60 seconds
            result = [None, None, None]
            read_tiva(ser_tiva, result)
            current_time = time.time() - start_time  # Relative time in seconds
            sample_count += 1
            buffer.append([sample_count, f"{current_time:.4f}"] + result)
            pwl_data.append((f"{current_time:.4f}", float(result[0]) if result[0] is not None else 0.0))  # Ensure voltage is float
            
            # Accumulate values for averaging
            if result[0] is not None:
                raw_values.append(float(result[0]))
            if result[1] is not None:
                filtered_values.append(float(result[1]))
            if result[2] is not None:
                temp_values.append(float(result[2]))
            
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
        else:
            avg_raw = 0.0
        if filtered_values:
            avg_filtered = np.mean(filtered_values)
        else:
            avg_filtered = 0.0
        if temp_values:
            avg_temp = np.mean(temp_values)
        else:
            avg_temp = 0.0
        
        with open(csv_filename, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Average', '', f"{avg_raw:.6f}", f"{avg_filtered:.6f}", f"{avg_temp:.2f}"])

        # Calculate sampling rate
        end_time = time.time()
        total_time = end_time - start_time
        sampling_rate = sample_count / total_time if total_time > 0 else 0
        
        print(f'Acquisition completed. Total samples: {sample_count}')
        print(f'Total time: {total_time:.2f} seconds')
        print(f'Sampling rate: {sampling_rate:.2f} samples/second')
        print(f'Data saved to {csv_filename}')
        print(f'Averages appended to CSV: Raw={avg_raw:.6f}, Filtered={avg_filtered:.6f}, Temp={avg_temp:.2f}')
        
        # Save to numpy array as well
        # Note: Since we're saving incrementally, we might need to load and save, but for simplicity, skip or modify
        # For now, just save the CSV
    except Exception as e:
        print(f"Error during acquisition: {e}")
    finally:
        if 'ser_tiva' in globals():
            ser_tiva.close()

if __name__ == "__main__":
    acquire_data()