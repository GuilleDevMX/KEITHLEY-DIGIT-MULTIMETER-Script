import serial
import struct
import time
import signal
import sys
import csv
import logging

# ========================= CONFIGURACIÓN =========================
class TivaConfig:
    SERIAL_PORT = 'COM6'
    BAUDRATE = 230400
    TIMEOUT = 1.0

class AlicatConfig:
    SERIAL_PORT = 'COM5'
    BAUDRATE = 115200
    TIMEOUT = 1.0

# ========================= CHECKSUM XOR =========================
def checksum_xor(data):
    cs = 0
    for byte in data:
        cs ^= byte
    return cs

# ========================= LEER TIVA =========================
def read_tiva(ser):
    """
    Lee datos del TIVA usando el protocolo:
    [0xAA] [4 bytes float1] [4 bytes float2] [1 byte XOR checksum] [0x41]
    Total: 11 bytes
    """
    ser.reset_input_buffer()
    ser.flushInput()
    try:
        # Sincronización con header 0xAA
        while True:
            byte = ser.read(1)
            if byte == b'\xAA':
                break

        # Leer los 10 bytes restantes
        remaining = ser.read(10)
        if len(remaining) != 10:
            return None, None

        packet = b'\xAA' + remaining  # Paquete completo: 11 bytes

        # Verificar estructura
        if packet[-1] != 0x41:
            return None, None

        # Extraer payload y checksum
        payload1_bytes = packet[1:5]  # 4 bytes del primer float
        payload2_bytes = packet[5:9]  # 4 bytes del segundo float
        checksum_recibido = packet[9]

        # Calcular checksum sobre ambos floats (8 bytes)
        payload_combined = payload1_bytes + payload2_bytes
        checksum_calculado = checksum_xor(payload_combined)

        # if checksum_calculado != checksum_recibido:
        #     return None, None

        # Desempaquetar los floats
        payload1 = struct.unpack('<f', payload1_bytes)[0]
        payload2 = struct.unpack('<f', payload2_bytes)[0]

        return payload1, payload2

    except Exception as e:
        print(f"Error leyendo TIVA: {e}")
        return None, None

# ========================= LOGGER =========================
def setup_logger(log_file):
    logger = logging.getLogger('AlicatTivaLogger')
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Handler para archivo
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

# ========================= FUNCIONES AUXILIARES =========================
def read_alicat_pressure(ser):
    """Lee la presión actual del Alicat"""
    try:
        response = ser.readline().decode('ascii', errors='ignore').strip()
        if response:
            parts = response.split()
            if len(parts) >= 3:
                return float(parts[1])  # Presión en kPa
    except Exception as e:
        print(f"Error leyendo Alicat: {e}")
    return None

# ========================= ESTABILIDAD DE PRESIÓN =========================
def stability_setpoint(ser_alicat, setpoint, threshold=0.002, expected_time=30, averaging_time=5):
    """Espera hasta que la presión se estabilice cerca del setpoint, verificando el promedio durante averaging_time.
    Una vez encontrada la estabilidad, debe mantenerla al menos 3 segundos; de lo contrario, repite."""
    start_time = time.time()
    pressures = []
    averaging_start = start_time
    stability_start_time = None
    while time.time() - start_time < expected_time:
        linea = ser_alicat.readline().decode('ascii', errors='ignore').strip()
        if not linea:
            continue
        campos = linea.split()
        if len(campos) >= 3:
            try:
                presion_actual = float(campos[1])
                pressures.append(presion_actual)
                current_time = time.time()
                if   current_time - averaging_start >= averaging_time and len(pressures) > 0:
                    avg_pressure = sum(pressures) / len(pressures)
                    if abs(avg_pressure - setpoint) <= threshold:
                        if stability_start_time is None:
                            stability_start_time = current_time
                            print(f"Estabilidad inicial detectada - Promedio: {avg_pressure:.3f} kPA (setpoint: {setpoint:.3f})")
                        elif current_time - stability_start_time >= 3.0:
                            ser_alicat.write(b"@@ A\r")
                            print(f"Presión estabilizada y mantenida por 3s - Promedio: {avg_pressure:.3f} kPA (setpoint: {setpoint:.3f})")
                            return True
                        # Continuar verificando durante los 3 segundos
                    else:
                        # Reset si sale del threshold
                        if stability_start_time is not None:
                            print(f"Estabilidad perdida - Promedio: {avg_pressure:.3f} kPA (setpoint: {setpoint:.3f})")
                        pressures = []
                        averaging_start = current_time
                        stability_start_time = None
            except (ValueError, IndexError):
                continue
    print(f"Tiempo de espera excedido para estabilización de presión: {expected_time}s")
    return False

# ========================= PUNTOS DE PRESIÓN =========================
def pressure_points(initial=0, final=6.78, step_size=10):
    """
    Crea puntos de presión equiespaciados
    Presión máxima del Alicat: 6.86466 kPa
    """
    if final > 6.86466:
        print(f"Ajustando presión final de {final} a 6.86466 kPa (máximo del Alicat)")
        final = 6.86466

    points = []
    num_steps = int(step_size)

    for i in range(num_steps + 1):
        pressure = initial + (final - initial) * (i / num_steps)
        points.append(round(pressure, 3))

    return points

# ========================= MAIN =========================
def main():
    # Configurar logger
    logger = setup_logger('alicat_tiva.log')

    # Manejo de señales
    def signal_handler(sig, frame):
        print("\nDeteniendo captura de datos...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Conectar dispositivos
        print("Conectando a TIVA y Alicat...")
        ser_tiva = serial.Serial(TivaConfig.SERIAL_PORT, TivaConfig.BAUDRATE, timeout=TivaConfig.TIMEOUT)
        ser_alicat = serial.Serial(port="COM5", baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=0.01)
        time.sleep(2)

        # Limpiar buffers
        ser_tiva.reset_input_buffer()

        print("Conexión establecida con TIVA y Alicat")
        ser_alicat.write(b"@@ A\r")  # Comando para detener el streaming de datos
        time.sleep(1)
        # Inicializar Alicat en 0 kPa
        print("Inicializando Alicat en 0 kPa...")
        ser_alicat.write(b"A S 0.000\r")
        print("Esperando 1 segundo para estabilización...")
        time.sleep(1)

        ser_alicat.write(b"A@ @\r")
        
        time.sleep(1)
        # Crear archivo CSV
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        csv_filename = f"datos_presion_tiva_{timestamp}.csv"
        headers = ["Tiempo_desde_inicio", "Payload1", "Payload2", "Presion_kPa"]

        with open(csv_filename, 'w', newline='') as csvfile:
            csvwriter = csv.writer(csvfile)
            csvwriter.writerow(headers)

        print(f"Archivo CSV creado: {csv_filename}")

        # Generar puntos de presión
        setpoints = pressure_points(initial=0, final=0.100, step_size=100)
        print(f"Puntos de presión a procesar: {setpoints}")

        # Variables de control
        start_time = time.time()
        last_pressure = None
        sample_count = 0

        # Procesar cada setpoint
        for setpoint in setpoints:
            print(f"\n{'='*50}")
            ser_alicat.write(b"@@ A\r")  # Comando para detener el streaming de datos
            time.sleep(1)

            print(f"Procesando setpoint: {setpoint:.3f} kPa")
            print(f"{'='*50}")

            # Establecer nuevo setpoint
            ser_alicat.write(f"A S {setpoint:.3f}\r".encode('ascii'))
            time.sleep(0.5)  # Pequeña espera para respuesta
            ser_alicat.write(b"A @ @\r")
            time.sleep(0.5)  # Pequeña espera para respuesta
            # Esperar estabilización
            # while not stability_setpoint(ser_alicat, setpoint, threshold=0.001, expected_time=20, averaging_time=5):
            #     time.sleep(0.01)
            # Monitorear cambios de presión de 1 Pa (0.001 kPa)
            pressure_threshold = 0.001  # 1 Pa = 0.001 kPa
            last_logged_pressure = None
            
            ser_alicat.write(b"A @ @\r")
            time.sleep(0.5)
            print(f"Monitoreando cambios de presión >= {pressure_threshold*1000:.0f} Pa...")

            # Capturar datos durante un período después de la estabilización
            monitoring_start = time.time()
            monitoring_duration = 60  # segundos de monitoreo por setpoint
            ser_alicat.write(b"A @ @\r")
            time.sleep(0.5)

            while time.time() - monitoring_start < monitoring_duration:
                # Leer presión actual del Alicat
                current_pressure = read_alicat_pressure(ser_alicat)
                if current_pressure is not None:
                    # Verificar si cambió al menos 1 Pa desde la última captura
                    if last_logged_pressure is None or abs(current_pressure - last_logged_pressure) >= pressure_threshold:
                        # Leer datos del TIVA
                        payload1, payload2 = read_tiva(ser_tiva)

                        if payload1 is not None and payload2 is not None:
                            # Calcular tiempo desde inicio
                            elapsed_time = time.time() - start_time

                            # Guardar en CSV
                            with open(csv_filename, 'a', newline='') as csvfile:
                                csvwriter = csv.writer(csvfile)
                                csvwriter.writerow([
                                    f"{elapsed_time:.3f}",
                                    f"{payload1:.6f}",
                                    f"{payload2:.6f}",
                                    f"{current_pressure:.6f}"
                                ])

                            sample_count += 1
                            last_logged_pressure = current_pressure

                            print(f"[{sample_count:4d}] T+{elapsed_time:7.3f}s | P1:{payload1:10.7f} | P2:{payload2:10.7f} | Pres:{current_pressure:8.3f} kPa")

        print(f"\n{'='*50}")
        print("CAPTURA COMPLETADA")
        print(f"{'='*50}")
        print(f"Total de muestras: {sample_count}")
        print(f"Archivo guardado: {csv_filename}")
        print(f"Tiempo total: {time.time() - start_time:.1f} segundos")

    except KeyboardInterrupt:
        print("\nInterrupción por usuario")
    except Exception as e:
        logger.error(f"Error durante la adquisición: {e}")
        print(f"Error: {e}")
    finally:
        # Cerrar conexiones
        try:
            if 'ser_tiva' in locals():
                ser_tiva.close()
            if 'ser_alicat' in locals():
                ser_alicat.write(b"@@ A\r")
                ser_alicat.close()
            print("Conexiones seriales cerradas")
        except:
            pass

if __name__ == "__main__":
    main()