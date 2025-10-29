import serial # permite comunicación serial
import time # para manejo de tiempos
import csv # para manejo de archivos CSV
import os # para verificar existencia de archivos
import threading # Permite ejecutar la adquisición en un hilo separado para no bloquear la interfaz gráfica
import tkinter as tk # Permite crear la ventana gráfica y los botones de control
import logging
import ast # para evaluación segura de expresiones literales
from acquisition import KeithleyAcquisition

# Configurar logging para adquisición
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/acquisition.log')
    ]
)
logger = logging.getLogger(__name__)


# Configuración de CSV y puertos
csv_file = f"Datos_{time.strftime('%Y%m%d_%H%M%S')}.csv" # Archivo CSV para guardar datos (valor por defecto)
# Parámetros de ciclo de histéresis
num_ciclos = 1
punto_inicio = 0
punto_final = 6.867
setpoint_intervalo = 60 # Intervalo en segundos para cambiar el setpoint
num_puntos_intermedios = 2
stability_time = 15  # Tiempo de estabilización en segundos después de cambiar el setpoint

# Modo de puntos intermedios
intermediate_mode = "automatic"  # "automatic" o "manual"
custom_points_text = "[0, 1, 2, 3, 4, 5, 6, 6.5, 6.8]"  # Puntos personalizados para modo manual

# Configuración de puertos seriales
alicat_port = "COM5"
tiva_port = "COM6"

# Configuración Keithley (simplificada para integración)
keithley_config = {
    'experiment_label': 'integrated_acquisition',
    'samples_per_count': 1,  # Una lectura por iteración para sincronizar
    'nplc_cycles': 1,
    'infinite_mode': False,
    'num_blocks': 1,  # No usado en este contexto
    'no_stats': True,
    'output_dir': '.',  # Directorio actual
    'quiet': True
}

# Variables de control globales
acquisition_running = False  # Bandera para saber si la adquisición está activa
acquisition_paused = False   # Bandera para saber si la adquisición está pausada
thread_acquisition = None # Variable donde se guarda el hilo de adquisición para poder detenerlo/join

# Variables globales para conexiones
ser_tiva_global = None
ser_alicat_global = None
keithley_acquirer_global = None

def ciclo(num_ciclos, punto_inicio, punto_final, num_puntos_intermedios):
    setpoints = []
    for _ in range(num_ciclos):
        # Barrido ascendente (incluyendo punto inicial y final)
        for i in range(num_puntos_intermedios + 1):
            sp = punto_inicio + (punto_final - punto_inicio) * i / num_puntos_intermedios
            setpoints.append(round(sp, 3))
        # Barrido descendente (incluyendo punto final y punto inicial para igual número de puntos)
        for i in range(num_puntos_intermedios + 1):
            sp = punto_final - (punto_final - punto_inicio) * i / num_puntos_intermedios
            setpoints.append(round(sp, 3))
    return setpoints

def generar_setpoints(num_ciclos, punto_inicio, punto_final, num_puntos_intermedios, intermediate_mode, custom_points_text):
    """Genera lista de setpoints basada en el modo seleccionado"""
    if intermediate_mode == "manual":
        # Usar puntos personalizados
        try:
            # Parsear la cadena de puntos personalizados
            import ast
            custom_points = ast.literal_eval(custom_points_text)
            if not isinstance(custom_points, list) or len(custom_points) < 2:
                raise ValueError("Puntos personalizados deben ser una lista con al menos 2 elementos")

            # Convertir a float y redondear
            custom_points = [round(float(sp), 3) for sp in custom_points]

            # Para cada ciclo, aplicar los puntos personalizados tanto para subida como bajada
            setpoints = []
            for _ in range(num_ciclos):
                # Subida: usar los puntos en orden
                setpoints.extend(custom_points)
                # Bajada: usar los puntos en orden inverso (excluyendo el último punto de subida para evitar duplicado)
                setpoints.extend(list(reversed(custom_points[:-1])))

            return setpoints

        except (ValueError, SyntaxError) as e:
            logger.warning(f"Error parsing custom points '{custom_points_text}': {e}. Using automatic mode.")
            # Fallback a modo automático
            return ciclo(num_ciclos, punto_inicio, punto_final, num_puntos_intermedios)
    else:
        # Modo automático
        return ciclo(num_ciclos, punto_inicio, punto_final, num_puntos_intermedios)

def read_tiva(ser_tiva, result):
    """Leer datos del TIVA de manera optimizada"""
    linea_raw = ser_tiva.readline().strip()
    if not linea_raw or len(linea_raw) < 12:
        result[:] = [None, None, None, None]
        return

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
            tiva_temp = TEMP_ALTO * 10 + TEMP_BAJO
            valor1 = linea_raw[11]
            TEMP1_ALTO = (valor1 >> 4) & 0x0F
            TEMP1_BAJO = valor1 & 0x0F
            tiva_temp += TEMP1_ALTO * 0.1 + TEMP1_BAJO * 0.01

            if linea_raw[0] == 45:  # Si es negativo
                tiva_raw = tiva_raw * -1

            if linea_raw[5] == 45:  # Si es negativo
                tiva_fir = tiva_fir * -1

            res = [None, None, None]
            res[:] = tiva_raw, tiva_fir, tiva_temp
            return res
        else:
            return [None, None, None, None]

    tiva_data = parse_tiva_data(linea_raw)
    com_tiva_raw = tiva_data[0]
    com_tiva_filtrado = tiva_data[1]
    com_tiva_temp = tiva_data[2]
    

    result[:] = [
        com_tiva_raw,
        com_tiva_filtrado,
        com_tiva_temp
        ]

def stability_setpoint(ser_alicat, setpoint, threshold=0.002, expected_time=30, averaging_time=5) -> bool:
    """Espera hasta que la presión se estabilice cerca del setpoint, verificando el promedio durante averaging_time"""
    ser_alicat.write(f"A S {setpoint:.1f}\r".encode('ascii'))
    start_time = time.time()
    pressures = []
    averaging_start = start_time
    while time.time() - start_time < expected_time:
        ser_alicat.write(b"A @ @\r")
        time.sleep(0.1)  # Pequeña espera para respuesta
        linea = ser_alicat.readline().decode('ascii', errors='ignore').strip()
        if not linea:
            continue
        campos = linea.split()
        if len(campos) >= 3:
            try:
                presion_actual = float(campos[1])
                pressures.append(presion_actual)
                current_time = time.time()
                if current_time - averaging_start >= averaging_time and len(pressures) > 0:
                    avg_pressure = sum(pressures) / len(pressures)
                    if abs(avg_pressure - setpoint) <= threshold:
                        ser_alicat.write(b"@@ A\r")
                        logger.info(f"Presión estabilizada - Promedio: {avg_pressure:.3f} kPA (setpoint: {setpoint:.3f})")
                        ser_alicat.write(f"A S {setpoint:.1f}\r".encode('ascii'))
                        return True
                    else:
                        # Reset para nueva ventana de promediado
                        pressures = []
                        averaging_start = current_time
            except (ValueError, IndexError):
                continue
    logger.warning(f"Tiempo de espera excedido para estabilización de presión: {expected_time}s")
    return False

def stability_by_voltage_reference_to_tiva(ser_tiva, voltage_reference=None, threshold=0.0001, num_of_samples=1000, expected_time=20) -> bool:
    """Espera hasta que la tensión de TIVA se estabilice cerca de la referencia de voltaje, verificando el promedio de diferencias absolutas durante una ventana de num_of_samples"""
    if voltage_reference is None:
        logger.error("voltage_reference no puede ser None")
        return False

    start_time = time.time()
    voltages = []  # Lista de diferencias absolutas
    while time.time() - start_time < expected_time:
        # Leer TIVA
        tiva_result = [None, None, None, None]
        read_tiva(ser_tiva, tiva_result)
        com_tiva_raw, com_tiva_filtrado, com_tiva_temp = tiva_result
        if com_tiva_filtrado is not None:
            diff = abs(com_tiva_filtrado - voltage_reference)
            voltages.append(diff)

            if len(voltages) >= num_of_samples:
                avg_difference = sum(voltages) / len(voltages)
                print(f"Averaging completed: avg_difference={avg_difference:.6f} V")
                if avg_difference <= threshold:
                    logger.info(f"Voltaje TIVA estabilizado - Desviación promedio: {avg_difference:.6f} V (referencia: {voltage_reference:.6f} V)")
                    return True
                else:
                    # Reset para nueva ventana de promediado
                    voltages = []
    logger.warning(f"Tiempo de espera excedido para estabilización de voltaje: {expected_time}s")
    return False

def read_alicat(ser_alicat, result):
    """Leer datos del Alicat de manera optimizada"""
    try:
        dato_alicat = ser_alicat.readline().decode('ascii', errors='ignore').strip()
        if not dato_alicat:
            result[:] = [None, None]
            return

        campos = dato_alicat.split()
        if len(campos) >= 3:
            try:
                result[:] = [float(campos[1]), float(campos[2])]
            except (ValueError, IndexError):
                result[:] = [None, None]
        else:
            result[:] = [None, None]
    except Exception:
        result[:] = [None, None]

def read_voltage_v_from_terminal() -> float:
    """Leer valor de voltaje desde la terminal de manera optimizada"""
    voltage_v = None
    while voltage_v is None:
        entrada = input("Por favor, ingrese el valor de voltaje para estabilización: ")
        try:
            voltage_v = float(entrada)
        except ValueError:
            print("Entrada inválida. Por favor, ingrese un número válido para voltaje.")
    return voltage_v

def read_keithley(keithley_acquirer, result):
    """Leer datos del Keithley de manera optimizada"""
    try:
        block_readings = keithley_acquirer.acquire_block(1)
        result[0] = block_readings[0] if block_readings else None
    except Exception:
        result[0] = None

def acquisition_loop(params):
    global acquisition_running, acquisition_paused
    global logger
    global ser_tiva_global, ser_alicat_global, keithley_acquirer_global

    # Extraer parámetros
    setpoint_inicial = params['setpoint_inicial']
    setpoint_final = params['setpoint_final']
    setpoint_intervalo = params['setpoint_intervalo']
    num_puntos_intermedios = params['num_puntos_intermedios']
    num_ciclos = params['num_ciclos']
    intermediate_mode = params['intermediate_mode']
    custom_points_text = params['custom_points_text']
    stability_time = params['stability_time'] if params['enable_stability'] else 0
    file_label = params.get('file_label', 'Datos')  # Usar 'Datos' como valor por defecto

    # Preparar archivo CSV con timestamp actual y etiqueta personalizada
    csv_file = f"{file_label}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    file_exists = os.path.isfile(csv_file)
    csv_f = open(csv_file, "a", newline="")
    csv_writer = csv.writer(csv_f)

    if not file_exists:
        csv_writer.writerow(["Timestamp", "Sample", "Ciclo", "Fase", "TIVA Voltage (V)", "TIVA Voltage w/FPB(V)","KEITHLEY Voltage (V)", "TIVA Temp (C)", "Alicat Presion (kPA)", "Alicat Setpoint (kPA)", "Setpoint Enviado (kPA)"])
        logger.info(f"Archivo CSV creado: {csv_file}")

    # Inicializar conexiones seriales optimizadas
    ser_tiva = serial.Serial(port=tiva_port, baudrate=115200, timeout=1)
    ser_alicat = serial.Serial(port="COM5", baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=0.01)

    # Asignar a variables globales para acceso desde detener_adquisicion
    ser_tiva_global = ser_tiva
    ser_alicat_global = ser_alicat

    # Generar lista de setpoints de manera optimizada
    setpoint_list = generar_setpoints(num_ciclos, setpoint_inicial, setpoint_final, num_puntos_intermedios, intermediate_mode, custom_points_text)
    logger.info(f"Setpoints generados: {setpoint_list}")
    # Calcular configuración de ciclos de manera más eficiente
    if intermediate_mode == "manual":
        custom_points = ast.literal_eval(custom_points_text)
        puntos_subida = len(custom_points)
        puntos_bajada = len(custom_points) - 1
    else:
        puntos_subida = puntos_bajada = num_puntos_intermedios + 1

    puntos_por_ciclo = puntos_subida + puntos_bajada

    ser_alicat.write(b"@@ A\r")  # Comando para iniciar comunicación

    # Inicializar variables de control
    current_setpoint_index = 0
    nuevo_setpoint = setpoint_list[0] if setpoint_list else setpoint_inicial
    time.sleep(0.5)  # Pequeña espera para asegurar que el comando se procese
    # Configurar setpoint inicial de manera optimizada
    ser_alicat.write(f"A S {nuevo_setpoint:.1f}\r".encode('ascii'))
    time.sleep(0.5)  # Pequeña espera para asegurar que el comando se procese
    keystone = None

    # Espera de estabilización inicial usando métodos específicos
    if stability_time > 0:
        logger.info(f"Iniciando estabilización inicial para setpoint: {nuevo_setpoint:.1f} kPA")
        while not stability_setpoint(ser_alicat, nuevo_setpoint, threshold=0.002, expected_time=stability_time):
            time.sleep(0.1)
        voltage_v = read_voltage_v_from_terminal()
        while not stability_by_voltage_reference_to_tiva(ser_tiva, voltage_v, threshold=0.0002, num_of_samples=200, expected_time=stability_time):
            time.sleep(0.1)

    # Logging de inicio optimizado
    logger.info(f"Adquisición iniciada - Archivo: {csv_file}")
    logger.info(f"Configuración: {num_ciclos} ciclos, {num_puntos_intermedios} puntos intermedios, Setpoint inicial: {nuevo_setpoint:.1f} kPA")
    time.sleep(1)
    ultimo_ajuste = time.time()
    sample_counter = 0
    ser_alicat.write(b"A @ @\r")  # Comando para iniciar lecturas
    try:
        while acquisition_running:
            if acquisition_paused:
                continue

            sample_counter += 1
            timestamp = time.strftime('%H:%M:%S')
            current_time = time.time()

            # Cálculo optimizado de ciclo y fase
            ciclo_num = (current_setpoint_index // puntos_por_ciclo) + 1
            posicion_en_ciclo = current_setpoint_index % puntos_por_ciclo
            fase = "subida" if posicion_en_ciclo < puntos_subida else "bajada"

            # Cambio de setpoint optimizado
            if current_time - ultimo_ajuste >= setpoint_intervalo:
                if current_setpoint_index + 1 < len(setpoint_list):
                    current_setpoint_index += 1
                    nuevo_setpoint = setpoint_list[current_setpoint_index]

                    if stability_time > 0:
                        logger.info(f"Cambio de setpoint - Ciclo: {ciclo_num}, Fase: {fase}, Setpoint: {nuevo_setpoint:.1f} kPA")

                    # Comando optimizado
                    ser_alicat.write(b"@@ A\r")
                    time.sleep(1) 
                    ser_alicat.write(f"A S {nuevo_setpoint:.3f}\r".encode('ascii'))

                    # Espera de estabilización usando métodos específicos
                    if stability_time > 0:
                        logger.info(f"Iniciando estabilización para setpoint: {nuevo_setpoint:.1f} kPA")
                        # Estabilizar presión del Alicat
                        while not stability_setpoint(ser_alicat, nuevo_setpoint, threshold=0.002, expected_time=stability_time):
                            time.sleep(0.1)
                        # Estabilizar voltaje TIVA respecto a Keithley
                        voltage_v = read_voltage_v_from_terminal()
                        tries = 0
                        while not stability_by_voltage_reference_to_tiva(ser_tiva, voltage_v, threshold=0.0002, num_of_samples=200, expected_time=stability_time):
                            if tries >= 5:
                                logger.warning("No se logró estabilizar el voltaje TIVA después de varios intentos.")
                                voltage_v = read_voltage_v_from_terminal()
                            tries += 1
                            time.sleep(0.1)
                        ser_alicat.write(b"A @ @\r")
                else:
                    ser_alicat.write(b"@@ A\r")
                    logger.info("Secuencia de adquisición completada")
                    acquisition_running = False
                    continue

                ultimo_ajuste = time.time()
            
            # Lectura de datos optimizada con hilos
            tiva_result = [None, None, None]
            alicat_result = [None, None]

            read_tiva(ser_tiva, tiva_result)
            read_alicat(ser_alicat, alicat_result)

            # Desempaquetar resultados
            com_tiva_raw, com_tiva_filtrado, com_tiva_temp = tiva_result
            alicat_presion, alicat_setpoint = alicat_result

            # Validación y guardado optimizado usando funciones de utilidad
            if validar_datos(com_tiva_raw, com_tiva_filtrado, com_tiva_temp, alicat_presion, alicat_setpoint, voltage_v):
                # Filtro de picos optimizado
                if not (abs(com_tiva_filtrado) > 0.1 and abs(com_tiva_temp) > 28):
                    fila_csv = formatear_fila_csv(
                        timestamp, sample_counter, ciclo_num, fase,
                        alicat_presion, alicat_setpoint, nuevo_setpoint,
                        com_tiva_raw, com_tiva_filtrado, voltage_v, 
                        com_tiva_temp
                    )
                    csv_writer.writerow(fila_csv)
                else:
                    logger.warning(f"Pico detectado - Filtrado: {com_tiva_filtrado:.6f}, Temp: {com_tiva_temp:.6f}")
            else:
                logger.warning("Datos incompletos - algunos sensores no respondieron")

    except Exception as e:
        logger.error(f"Error en adquisición: {e}")
    finally:
        # Limpieza optimizada de recursos
        if ser_tiva_global:
            ser_tiva_global.close()
            ser_tiva_global = None
        if ser_alicat_global:
            ser_alicat_global.close()
            ser_alicat_global = None
        csv_f.close()
        if keithley_acquirer_global:
            keithley_acquirer_global._disconnect_instrument()
            keithley_acquirer_global = None
        logger.info("Adquisición finalizada - Recursos liberados")

def iniciar_adquisicion(params):
    """Iniciar adquisición de manera optimizada"""
    global acquisition_running, thread_acquisition
    if not acquisition_running:
        acquisition_running = True
        thread_acquisition = threading.Thread(target=acquisition_loop, args=(params,))
        thread_acquisition.start()
        print("Adquisición iniciada.")

def formatear_fila_csv(timestamp, sample, ciclo, fase, alicat_presion, alicat_setpoint, nuevo_setpoint, *valores):
    """Formatear fila CSV de manera optimizada"""
    return [timestamp, sample, ciclo, fase] + [f"{v:.6f}" if isinstance(v, (int, float)) and v is not None else str(v) for v in valores] + [alicat_presion, alicat_setpoint, nuevo_setpoint]

def detener_adquisicion():
    """Detener adquisición de manera optimizada"""
    global acquisition_running, thread_acquisition
    global ser_tiva_global, ser_alicat_global, keithley_acquirer_global
    acquisition_running = False
    if thread_acquisition:
        thread_acquisition.join()
    # Cerrar comunicaciones seriales
    if ser_tiva_global:
        ser_tiva_global.close()
        ser_tiva_global = None
    if ser_alicat_global:
        ser_alicat_global.write(b"@@ A\r")
        ser_alicat_global.close()
        ser_alicat_global = None
    print("Adquisición detenida.")

def pausar_reanudar_adquisicion():
    """Pausar/reanudar adquisición de manera optimizada"""
    global acquisition_paused
    acquisition_paused = not acquisition_paused
    print("Adquisición pausada." if acquisition_paused else "Adquisición reanudada.")

def validar_datos(*valores):
    """Validar que todos los valores no sean None de manera optimizada"""
    return all(v is not None for v in valores)

def calcular_promedio(valores):
    """Calcular promedio de valores válidos de manera optimizada"""
    valores_validos = [v for v in valores if v is not None]
    return sum(valores_validos) / len(valores_validos) if valores_validos else None
