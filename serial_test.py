import serial
import struct
import time
import signal
import sys
import csv

# ========================= CONFIGURACIÓN =========================
SERIAL_PORT = 'COM6'
BAUDRATE = 230400
TIMEOUT = 1.0

# ========================= TABLA CRC (perfecta) =========================
crc16_table = [
    0x0000,0x1021,0x2042,0x3063,0x4084,0x50A5,0x60C6,0x70E7,0x8108,0x9129,0xA14A,0xB16B,0xC18C,0xD1AD,0xE1CE,0xF1EF,
    0x1231,0x0210,0x3273,0x2252,0x52B5,0x4294,0x72F7,0x62D6,0x9339,0x8318,0xB37B,0xA35A,0xD3BD,0xC39C,0xF3FF,0xE3DE,
    0x2462,0x3443,0x0420,0x1401,0x64E6,0x74C7,0x44A4,0x5485,0xA56A,0xB54B,0x8528,0x9509,0xE5EE,0xF5CF,0xC5AC,0xD58D,
    0x3653,0x2672,0x1611,0x0630,0x76D7,0x66F6,0x5695,0x46B4,0xB75B,0xA77A,0x9719,0x8738,0xF7DF,0xE7FE,0xD79D,0xC7BC,
    0x48C4,0x58E5,0x6886,0x78A7,0x0840,0x1861,0x2802,0x3823,0xC9CC,0xD9ED,0xE98E,0xF9AF,0x8948,0x9969,0xA90A,0xB92B,
    0x5AF5,0x4AD4,0x7AB7,0x6A96,0x1A71,0x0A50,0x3A33,0x2A12,0xDBFD,0xCBDC,0xFBBF,0xEB9E,0x9B79,0x8B58,0xBB3B,0xAB1A,
    0x6CA6,0x7C87,0x4CE4,0x5CC5,0x2C22,0x3C03,0x0C60,0x1C41,0xEDAE,0xFD8F,0xCDEC,0xDDCD,0xAD2A,0xBD0B,0x8D68,0x9D49,
    0x7E97,0x6EB6,0x5ED5,0x4EF4,0x3E13,0x2E32,0x1E51,0x0E70,0xFF9F,0xEFBE,0xDFDD,0xCFFC,0xBF1B,0xAF3A,0x9F59,0x8F78,
    0x9188,0x81A9,0xB1CA,0xA1EB,0xD10C,0xC12D,0xF14E,0xE16F,0x1080,0x00A1,0x30C2,0x20E3,0x5004,0x4025,0x7046,0x6067,
    0x83B9,0x9398,0xA3FB,0xB3DA,0xC33D,0xD31C,0xE37F,0xF35E,0x02B1,0x1290,0x22F3,0x32D2,0x4235,0x5214,0x6277,0x7256,
    0xB5EA,0xA5CB,0x95A8,0x8589,0xF56E,0xE54F,0xD52C,0xC50D,0x34E2,0x24C3,0x14A0,0x0481,0x7466,0x6447,0x5424,0x4405,
    0xA7DB,0xB7FA,0x8799,0x97B8,0xE75F,0xF77E,0xC71D,0xD73C,0x26D3,0x36F2,0x0691,0x16B0,0x6657,0x7676,0x4615,0x5634,
    0xD94C,0xC96D,0xF90E,0xE92F,0x99C8,0x89E9,0xB98A,0xA9AB,0x5844,0x4865,0x7806,0x6827,0x18C0,0x08E1,0x3882,0x28A3,
    0xCB7D,0xDB5C,0xEB3F,0xFB1E,0x8BF9,0x9BD8,0xABBB,0xBB9A,0x4A75,0x5A54,0x6A37,0x7A16,0x0AF1,0x1AD0,0x2AB3,0x3A92,
    0xFD2E,0xED0F,0xDD6C,0xCD4D,0xBDAA,0xAD8B,0x9DE8,0x8DC9,0x7C26,0x6C07,0x5C64,0x4C45,0x3CA2,0x2C83,0x1CE0,0x0CC1,
    0xEF1F,0xFF3E,0xCF5D,0xDF7C,0xAF9B,0xBFBA,0x8FD9,0x9FF8,0x6E17,0x7E36,0x4E55,0x5E74,0x2E93,0x3EB2,0x0ED1,0x1EF0
]

# ========================= CRC CORREGIDO =========================
def calcular_crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc = (crc << 8) ^ crc16_table[( (crc >> 8) ^ b) & 0xFF]
    return crc & 0xFFFF 

# ========================= MAIN CORREGIDO =========================
def main():
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    print("=== LECTOR TIVA TM4C123 - Versión FINAL CORREGIDA ===")
    print(f"Puerto: {SERIAL_PORT} @ {BAUDRATE} baud")

    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
    time.sleep(2)
    ser.reset_input_buffer()
    print("Conectado y buffer limpiado. Esperando paquetes...\n")

    # Crear archivo CSV
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    csv_filename = f"tiva_data_{timestamp}.csv"
    #   SendSensorPacket(Tension_AIN_DIF, current_press_pa, Press_Conver, press_cmh2O, NTC_Temp, 0);

    headers = ["Timestamp", "Elapsed_Time", "Vdif", "Presion kPa", "Presion Pa", "Presion cmH2O", "Temperatura C", "Iexc mA"]

    try:
        with open(csv_filename, 'w', newline='') as csvfile:
            csvwriter = csv.writer(csvfile)
            csvwriter.writerow(headers)

        print(f"Archivo CSV creado: {csv_filename}")
        print("Headers:", ", ".join(headers))
        print("-" * 80)

        count = 0
        t0 = time.time()

        while True:
            # -------- 1. Sincronización con header 0xAA 0x55 --------
            ser.reset_input_buffer()

            while True:
                if ser.read(1) == b'\xAA':
                    if ser.read(1) == b'\x55':
                        break

            # -------- 2. Leer los 26 bytes completos (24 + 2 CRC) --------
            packet = ser.read(26)
            if len(packet) != 26:
                print(f"Paquete incompleto: {len(packet)} bytes")
                continue

            # -------- 3. Separar payload y CRC --------
            payload = packet[:24]        # 6 floats = 24 bytes
            crc_recibido = struct.unpack('<H', packet[24:26])[0]

            # -------- 4. Verificar CRC --------
            crc_calculado = calcular_crc16_ccitt(payload)

            if crc_calculado != crc_recibido:
                print(f"CRC ERROR → Recibido: 0x{crc_recibido:04X} | Calculado: 0x{crc_calculado:04X}")
                continue

            # -------- 5. Desempaquetar los 6 floats --------
            v_dif, v_a, v_b, temp, comp, i_exc = struct.unpack('<6f', payload)
            count += 1
            elapsed = time.time() - t0
            rate = count / elapsed if elapsed > 0 else 0

            # -------- 6. Obtener timestamp y guardar en CSV --------
            current_timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            # headers = ["Timestamp", "Elapsed_Time", "Vdif", "Presion kPa", "Presion Pa", "Presion cmH2O", "Temperatura C", "Iexc mA"]

            # Guardar en CSV
            with open(csv_filename, 'a', newline='') as csvfile:
                csvwriter = csv.writer(csvfile)
                csvwriter.writerow([
                    current_timestamp,
                    f"{elapsed:.3f}",
                    f"{v_dif}",
                    f"{v_a}",
                    f"{v_b}",
                    f"{temp}",
                    f"{comp}",
                    f"{i_exc:.6f}"
                ])

            # -------- 7. Mostrar bonito --------
            print(f"\r[{count:5d}] Vdif={v_dif:9.8f}  Press={v_a:8.8f} kPa  Press={v_b:8.8f} Pa  "
                  f"Press={temp:6.8f} cmH2O  Temp={comp:8.8f} °C  Iexc={i_exc:8.8f}  "
                  f"→ {rate:5.1f} Hz", end='')

    except KeyboardInterrupt:
        print(f"\n\nInterrupción por usuario.")
        print(f"Total de muestras guardadas: {count}")
        print(f"Archivo CSV: {csv_filename}")
        print(f"Tiempo total: {elapsed:.1f} segundos")
    finally:
        ser.close()

if __name__ == "__main__":
    main()