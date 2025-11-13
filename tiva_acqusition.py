import serial
import csv
import numpy as np
import time
import threading
import os
import signal
import sys
import struct
from datetime import datetime

# === CONFIGURACIÓN GLOBAL ===
SERIAL_PORT = 'COM6'      # Cambia si usas otro puerto
BAUDRATE = 230400
TIMEOUT = 1.0
CSV_BUFFER_SIZE = 20      # Guarda cada 20 muestras

acquisition_running = False
ser_tiva = None

# === CRC-16-CCITT (igual que en Tiva C) ===
def calcular_crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

# === Validar y decodificar paquete de 12 bytes ===
def recibir_paquete(data_12bytes: bytes):
    if len(data_12bytes) != 12 or data_12bytes[10:] != b'\r\n':
        return None, None

    payload = data_12bytes[:8]
    crc_recibido = int.from_bytes(data_12bytes[8:10], 'little')
    crc_calculado = calcular_crc16_ccitt(payload)

    if crc_recibido != crc_calculado:
        print(f"CRC error: recibido 0x{crc_recibido:04X}, calculado 0x{crc_calculado:04X}")
        return None, None

    voltage, temperature = struct.unpack('<ff', payload)
    return voltage, temperature

# === Manejador de Ctrl+C ===
def signal_handler(sig, frame):
    print("\nInterrupción detectada. Terminando...")
    stop_acquisition()
    sys.exit(0)

def setup_signal_handler():
    signal.signal(signal.SIGINT, signal_handler)

# === Configurar puerto serial ===
def setup_serial():
    global ser_tiva
    try:
        ser_tiva = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=TIMEOUT
        )
        time.sleep(2)
        print(f"Conexión serial establecida en {SERIAL_PORT} @ {BAUDRATE} baudios")
        return True
    except serial.SerialException as e:
        print(f"Error: No se pudo abrir {SERIAL_PORT}: {e}")
        print("   Verifica que el Tiva esté conectado y el puerto sea correcto.")
        return False

# === Iniciar adquisición ===
def start_acquisition():
    global acquisition_running
    if acquisition_running:
        print("Adquisición ya en curso.")
        return
    acquisition_running = True
    threading.Thread(target=acquire_data, daemon=True).start()

# === Detener adquisición ===
def stop_acquisition():
    global acquisition_running
    acquisition_running = False
    if ser_tiva and ser_tiva.is_open:
        try:
            ser_tiva.close()
            print("Puerto serial cerrado.")
        except:
            pass

def conversion_counts_to_voltage(counts):
    # Suponiendo que los counts son de un ADC de 24 bits con referencia de 2.5V, PGA = 32
    V_ref = 5
    pga = 32
    max_counts = 2**24 - 1
    voltage = (counts / max_counts) * V_ref / pga
    return voltage

# === Función principal de adquisición ===
def acquire_data():
    global acquisition_running, ser_tiva

    if not setup_serial():
        acquisition_running = False
        return

    # --- Nombre de archivos con timestamp ---
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    csv_filename = f'tiva_data_{timestamp}.csv'
    pwl_filename = f'tiva_pwl_{timestamp}.pwl'

    # --- Archivos ---
    with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Muestra', 'Tiempo (s)', 'Voltaje (V)', 'Temperatura (°C)'])

    with open(pwl_filename, 'w', encoding='utf-8') as f:
        f.write("* PWL file for LTspice - Voltaje vs Tiempo\n")
        f.write("* Time(s)  Voltage(V)\n")

    # --- Variables de adquisición ---
    start_time = time.time()
    sample_count = 0
    buffer = []
    voltages = []
    temperatures = []
    acquisition_running = True

    print("Adquisición iniciada por 10 segundos. Presiona Ctrl+C para detener antes.")

    try:
        while acquisition_running and (time.time() - start_time) < 60.0:
            try:
                # Leer paquete completo (12 bytes)
                raw_line = ser_tiva.readline()
                if len(raw_line) != 12:
                    print(f"Paquete inválido: longitud {len(raw_line)}, esperado 12")
                    time.sleep(0.001)
                    continue

                current_time = time.time() - start_time
                voltage, temperature = recibir_paquete(raw_line)

                if voltage is not None and temperature is not None:
                    # --- Guardar en buffer ---
                    buffer.append([
                        sample_count,
                        f"{current_time:.6f}",
                        f"{voltage:.6f}",
                        f"{temperature:.3f}"
                    ])
                    voltages.append(voltage)
                    temperatures.append(temperature)

                    # --- Guardar en PWL (solo voltaje) ---
                    with open(pwl_filename, 'a', encoding='utf-8') as f:
                        f.write(f"{current_time:.6f} {voltage:.6f}\n")

                    sample_count += 1
                else:
                    # Paquete corrupto: registrar como error (opcional)
                    pass

                # --- Guardar en CSV cada N muestras ---
                if len(buffer) >= CSV_BUFFER_SIZE:
                    with open(csv_filename, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerows(buffer)
                    buffer.clear()

                time.sleep(0.001)  # ~1kHz max

            except serial.SerialException:
                print("Error de comunicación serial.")
                break
            except Exception as e:
                print(f"Error inesperado: {e}")
                break

        # --- Guardar datos restantes ---
        if buffer:
            with open(csv_filename, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(buffer)

        # --- Estadísticas finales ---
        total_time = time.time() - start_time
        sampling_rate = sample_count / total_time if total_time > 0 else 0

        if voltages:
            avg_voltage = np.mean(voltages)
            std_voltage = np.std(voltages)
            avg_temp = np.mean(temperatures)
            std_temp = np.std(temperatures)
        else:
            avg_voltage = std_voltage = avg_temp = std_temp = 0.0

        # --- Escribir resumen en CSV ---
        with open(csv_filename, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([])
            writer.writerow(['--- RESUMEN ---'])
            writer.writerow(['Muestras totales', sample_count])
            writer.writerow(['Tiempo total (s)', f"{total_time:.3f}"])
            writer.writerow(['Frecuencia (Hz)', f"{sampling_rate:.2f}"])
            writer.writerow(['Voltaje promedio (V)', f"{avg_voltage:.6f}"])
            writer.writerow(['Voltaje desv. std', f"{std_voltage:.6f}"])
            writer.writerow(['Temperatura promedio (°C)', f"{avg_temp:.3f}"])
            writer.writerow(['Temperatura desv. std', f"{std_temp:.3f}"])

        print("\n" + "="*50)
        print("ADQUISICIÓN COMPLETADA")
        print(f"   Archivo CSV: {csv_filename}")
        print(f"   Archivo PWL: {pwl_filename}")
        print(f"   Muestras: {sample_count}")
        print(f"   Tiempo: {total_time:.2f} s")
        print(f"   Frecuencia: {sampling_rate:.2f} Hz")
        print(f"   Voltaje promedio: {conversion_counts_to_voltage(avg_voltage):.6f} V")
        print(f"   Temperatura promedio: {avg_temp:.3f} °C")
        print("="*50)

    except Exception as e:
        print(f"Error crítico: {e}")
    finally:
        acquisition_running = False
        if ser_tiva and ser_tiva.is_open:
            ser_tiva.close()
            print("Puerto serial cerrado.")

# === MAIN ===
if __name__ == "__main__":
    setup_signal_handler()
    print("Iniciando adquisición de datos desde Tiva C (Voltaje + Temperatura) - 10 segundos")
    print(f"Puerto: {SERIAL_PORT} | Baudios: {BAUDRATE}")
    print("Presiona Ctrl+C para detener.\n")

    try:
        acquire_data()
    except KeyboardInterrupt:
        print("\nDetención solicitada por el usuario.")
    except Exception as e:
        print(f"Error fatal: {e}")
        sys.exit(1)