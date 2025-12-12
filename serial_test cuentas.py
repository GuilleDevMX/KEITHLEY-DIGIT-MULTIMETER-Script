import serial
import struct
import time
import signal
import sys
import csv
import os

# ========================= CONFIGURACIÓN =========================
SERIAL_PORT = 'COM7'
BAUDRATE = 230400
TIMEOUT = 1.0
NUM_SAMPLES = 1000  # Número de muestras a tomar

# ========================= CHECKSUM XOR =========================
def checksum_xor(data: bytes) -> int:
    cs = 0
    for b in data:
        cs ^= b
    return cs

# ========================= MAIN CORREGIDO =========================
def main():
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    print("=== LECTOR TIVA TM4C123 - Nuevo Protocolo UART ===")
    print(f"Puerto: {SERIAL_PORT} @ {BAUDRATE} baud")
    print(f"Número de muestras a tomar: {NUM_SAMPLES}")
    print("Protocolo: [0xAA] [4 bytes float] [1 byte XOR checksum] [0x41]")

    # Crear archivo CSV
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    csv_filename = f"cuentas_tiva_{timestamp}.csv"
    csv_file = open(csv_filename, 'w', newline='')
    csv_writer = csv.writer(csv_file)
    
    # Escribir headers
    csv_writer.writerow(["Sample", "Valor", "Timestamp", "Rate_Hz"])
    
    print(f"Archivo CSV creado: {csv_filename}")
    print("Conectando al puerto serial...")

    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
        time.sleep(2)
        ser.reset_input_buffer()
        print("Conectado y buffer limpiado. Iniciando adquisición...\n")

        count = 0
        t0 = time.time()

        while count < NUM_SAMPLES:
            # -------- 1. Sincronización con header 0xAA --------
            while True:
                byte = ser.read(1)
                if byte == b'\xAA':
                    break

            # -------- 2. Leer los 6 bytes restantes (4 float + 1 checksum + 1 end) --------
            remaining = ser.read(6)
            if len(remaining) != 6:
                print(f"Paquete incompleto: {len(remaining)} bytes (esperado 6)")
                continue

            packet = b'\xAA' + remaining  # Paquete completo: 7 bytes

            # -------- 3. Verificar estructura --------
            if packet[-1] != 0x41:
                print(f"Byte de fin incorrecto: 0x{packet[-1]:02X} (esperado 0x41)")
                continue

            # -------- 4. Extraer payload y checksum --------
            payload = packet[1:5]  # 4 bytes del float
            checksum_recibido = packet[5]

            # -------- 5. Calcular checksum --------
            checksum_calculado = checksum_xor(payload)

            if checksum_calculado != checksum_recibido:
                print(f"Checksum ERROR → Recibido: 0x{checksum_recibido:02X} | Calculado: 0x{checksum_calculado:02X}")
                continue

            # -------- 6. Desempaquetar el float --------
            try:
                valor = struct.unpack('<f', payload)[0]
                count += 1
                elapsed = time.time() - t0
                rate = count / elapsed if elapsed > 0 else 0
                
                # Obtener timestamp actual
                current_time = time.strftime('%H:%M:%S')

                # -------- 7. Guardar en CSV --------
                csv_writer.writerow([count, f"{valor:.7f}", current_time, f"{rate:.1f}"])
                
                # -------- 8. Mostrar progreso --------
                if count % 100 == 0 or count == NUM_SAMPLES:
                    print(f"\r[{count:4d}/{NUM_SAMPLES}] Valor={valor:9.7f}  → {rate:5.1f} Hz", end='', flush=True)

            except struct.error as e:
                print(f"Error desempaquetando float: {e}")
                continue

        # Finalización exitosa
        print(f"\n\n=== Adquisición completada ===")
        print(f"Total de muestras: {count}")
        total_time = time.time() - t0
        avg_rate = count / total_time if total_time > 0 else 0
        print(f"Tiempo total: {total_time:.2f} segundos")
        print(f"Frecuencia promedio: {avg_rate:.1f} Hz")
        print(f"Datos guardados en: {csv_filename}")

    except KeyboardInterrupt:
        print(f"\n\nInterrupción por usuario. Muestras tomadas: {count}")
    except Exception as e:
        print(f"\n\nError: {e}")
    finally:
        # Cerrar recursos
        if 'ser' in locals():
            ser.close()
            print("Puerto serial cerrado.")
        if 'csv_file' in locals():
            csv_file.close()
            print("Archivo CSV cerrado.")

if __name__ == "__main__":
    main()