"""
Sistema de Calibración PID para Controlador Alicat
Realiza calibración automática de parámetros PID para control de flujo/presión
"""
import serial
import time
import csv
import os
import threading
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager
import numpy as np

class AlicatPIDError(Exception):
    """Excepción base para errores del sistema Alicat"""
    pass


class AlicatConnectionError(AlicatPIDError):
    """Error de conexión con el controlador Alicat"""
    pass


class AlicatCalibrationError(AlicatPIDError):
    """Error durante la calibración PID"""
    pass


class AlicatController:
    """Clase para control y calibración de controlador Alicat"""

    def __init__(self, port: str = "COM5", baudrate: int = 115200, unit_id: str = "A"):
        self.port = port
        self.baudrate = baudrate
        self.unit_id = unit_id
        self.serial_conn = None
        self.logger = self._setup_logging()
        self._initialize_commands()

    def _setup_logging(self) -> logging.Logger:
        """Configura el sistema de logging"""
        logger = logging.getLogger('AlicatPID')
        logger.setLevel(logging.INFO)

        # Crear directorio de logs si no existe
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Handler para archivo
        log_file = os.path.join(log_dir, f'alicat_calibration_{datetime.now().strftime("%Y%m%d")}.log')
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)

        # Handler para consola
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # Formato
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger

    def _initialize_commands(self):
        """Inicializa el diccionario de comandos de Alicat"""
        # DATA READINGS
        self.commands = {
            "auto_tare": "unit_id ZCA enable delay",  # Auto-tare command for controllers
            "data_frame_config": "unit_id FDF format",  # Configure data frame for all devices
            "data_frame_query": "unit_id ?? D*",  # Query data frame for all devices
            "eng_units_query_change": "unit_id DCU statistic_value group unit_value override",  # Query or change engineering units
            "flow_pressure_avg_query": "unit_id DCA statistic_value average_timing",  # Query flow or pressure average
            "full_scale_values": "unit_id FPF statistic_value unit_value",  # Set full-scale values
            "poll_device_data": "unit_id",  # Poll device data
            "power_up_tare": "unit_id ZCP enable",  # Power-up tare for all devices
            "request_data": "unit_id DV time statistic1 statistic2 … statistic13",  # Request data
            "start_streaming": "unit_id @ @",  # Start streaming
            "stp_ntp_pressure_change": "unit_id DCFRP stp_or_ntp unit_value pressure",  # STP/NTP pressure change for mass flow
            "stp_ntp_temp_change": "unit_id DCFRT stp_or_ntp unit_value temperature",  # STP/NTP temperature change
            "stop_streaming": "@@ new_unit_id",  # Stop streaming
            "zero_band_query_change": "unit_id DCZ 0 zero_band",  # Query or change zero band
        }

        # GAS
        self.commands.update({
            "active_gas": "unit_id GS",  # Query active gas for mass flow
            "available_gases": "unit_id ?? G*",  # Query available gases
            "set_gas": "unit_id G gas_number",  # Set gas for mass flow
        })

        # SETPOINT
        self.commands.update({
            "change_setpoint": "unit_id S setpoint_value",  # Change setpoint for controllers
            "query_change_setpoint": "unit_id LS setpoint_value units_value",  # Query or change setpoint
            "power_up_setpoint": "unit_id SPUE setpoint_value",  # Power-up setpoint
            "setpoint_source": "unit_id LSS mode",  # Setpoint source
        })

        # GAS AND COMPOSER MIXTURES
        self.commands.update({
            "create_composer_mixture": "unit_id GM mix_name mix_number gas1% gas1# gas2% gas2# … gas5% gas5#",  # Create COMPOSER gas mixture
            "delete_gas_mixture": "unit_id GD gas_number",  # Delete gas mixture
            "query_gas_mixture": "unit_id GC gas_number",  # Query gas mixture
        })

        # TARES
        self.commands.update({
            "tare_absolute_pressure": "unit_id PC",  # Tare absolute pressure with barometer
            "tare_flow": "unit_id V",  # Tare flow
            "tare_gauge_diff_pressure": "unit_id P",  # Tare gauge/differential pressure
        })

        # TOTALIZER
        self.commands.update({
            "configure_totalizer": "unit_id TC totalizer1_or_totalizer2 flow_statistic_value mode limit_mode number_of_digits decimal_place",  # Configure totalizer
            "reset_totalizer": "unit_id T totalizer1_or_totalizer2",  # Reset totalizer
            "reset_totalizer_peak": "unit_id TP totalizer1_or_totalizer2",  # Reset totalizer peak
            "save_totalizer": "unit_id TCR enable_or_disable",  # Save totalizer
        })

        # VALVE CONTROL
        self.commands.update({
            "cancel_valve_hold": "unit_id C",  # Cancel valve hold
            "exhaust_open_valve": "unit_id E",  # Exhaust (open downstream valve) for multi-valve controllers
            "hold_valve_position": "unit_id HP",  # Hold valve(s) position
            "hold_valve_closed": "unit_id HC",  # Hold valve(s) closed
            "query_valve_drive_state": "unit_id VD",  # Query valve drive state
        })

        # CONTROL SETUP
        self.commands.update({
            "batching": "unit_id TB totalizer1_or_2 batch_volume unit_value",  # Batching
            "deadband_limit": "unit_id LCDB save deadband_limit",  # Deadband limit
            "deadband_mode": "unit_id LCDM mode",  # Deadband mode
            "loop_control_algorithm": "unit_id LCA algorithm",  # Loop control algorithm
            "loop_control_range": "unit_id LR loop_variable unit_value",  # Loop control range
            "loop_control_variable": "unit_id LV loop_variable",  # Loop control variable
            "max_ramp_rate": "unit_id SR max_ramp_rate unit_time",  # Max ramp rate
            "pd_pdf_gains": "unit_id LCGD 0 save p_gain d_gain",  # PD/PDF gains
            "read_pd_pdf_gains": "unit_id LCGD",  # Read PD/PDF gains
            "pd2i_gains": "unit_id LCG 0 save p_gain i_gain d_gain",  # PD2I gains
            "read_pd2i_gains": "unit_id LCG",  # Read PD2I gains  
            "overpressure_limit": "unit_id OPL pressure_limit",  # Overpressure limit
            "ramping_options": "unit_id LSRC ramp_up ramp_down zero_ramp power_up_ramp",  # Ramping options
            "valve_offset": "unit_id LCVO 0 save initial_offset closed_offset",  # Valve offset
            "zero_pressure_control": "unit_id LCZA enable_or_disable",  # Zero pressure control
            "query_unit_id": "unit_id",  # Query unit ID
            "query_loop_algorithm": "unit_id LCA",  # Query loop control algorithm
            "read_pd_pdf_gains": "unit_id LCGD",  # Read PD/PDF gains
        })

        # DEVICE SETUP
        self.commands.update({
            "analog_output_source": "unit_id ASOCV output_source value unit_value",  # Analog output source
            "baud_rate_settings": "unit_id NCB new_baud_rate",  # Baud rate settings
            "blink_display": "unit_id FFP duration",  # Blink display
            "change_unit_id": "unit_id @ new_unit_id",  # Change unit ID
            "firmware_version": "unit_id VE",  # Firmware version
            "lock_device_display": "unit_id L",  # Lock device display
            "manufacturing_info": "unit_id ??M*",  # Manufacturing info
            "remote_tare_settings": "unit_id ASRCA action",  # Remote tare settings
            "restore_factory_settings": "unit_id FACTORY RESTORE ALL",  # Restore factory settings
            "streaming_rate_settings": "unit_id NCS interval",  # Streaming rate settings
            "unlock_device_display": "unit_id U",  # Unlock device display
            "user_data": "unit_id UD slot value",  # User data
        })

    def _format_command(self, command_key: str, **kwargs) -> str:
        """Formatea un comando reemplazando unit_id y otros parámetros"""
        if command_key not in self.commands:
            raise ValueError(f"Comando desconocido: {command_key}")

        # Obtener el template del comando
        command_template = self.commands[command_key]

        # Reemplazar unit_id
        formatted_command = command_template.replace("unit_id", self.unit_id)

        # Reemplazar otros parámetros si se proporcionan
        for param_name, value in kwargs.items():
            # Reemplazar el nombre del parámetro directamente (sin llaves)
            formatted_command = formatted_command.replace(param_name, str(value))

        return formatted_command

    def get_firmware_version(self) -> str:
        """Obtiene la versión del firmware del dispositivo"""
        command = self._format_command("firmware_version")
        return self._send_command(command)

    def get_manufacturing_info(self) -> str:
        """Obtiene información de manufactura del dispositivo"""
        command = self._format_command("manufacturing_info")
        return self._send_command(command)

    def get_unit_id_info(self) -> Dict[str, float]:
        """Obtiene información del unit ID incluyendo ganancias PID
        
        Returns:
            Dict con 'unit_id', 'p_gain', 'd_gain' y 'reserved'
        """
        command = self._format_command("query_unit_id")
        response = self._send_command(command)
        
        if response:
            # Parse response: unit_id p_gain d_gain reserved
            parts = response.strip().split()
            if len(parts) >= 4:
                try:
                    return {
                        'unit_id': parts[0],
                        'p_gain': float(parts[1]),
                        'd_gain': float(parts[2]),
                        'reserved': float(parts[3])
                    }
                except (ValueError, IndexError):
                    pass
        
        return {'unit_id': 'Unknown', 'p_gain': 0.0, 'd_gain': 0.0, 'reserved': 0.0}

    def get_loop_control_algorithm(self) -> Dict[str, any]:
        """Obtiene el algoritmo de control de lazo actual
        
        Returns:
            Dict con 'unit_id', 'algorithm_code', 'algorithm_name'
        """
        command = self._format_command("query_loop_algorithm")
        response = self._send_command(command)
        
        if response:
            # Parse response: unit_id algorithm_code
            parts = response.strip().split()
            if len(parts) >= 2:
                try:
                    algorithm_code = int(parts[1])
                    algorithm_names = {
                        1: "PD/PDF algorithm",
                        2: "PD2I algorithm"
                    }
                    return {
                        'unit_id': parts[0],
                        'algorithm_code': algorithm_code,
                        'algorithm_name': algorithm_names.get(algorithm_code, "Unknown")
                    }
                except (ValueError, IndexError):
                    pass
        
        return {'unit_id': 'Unknown', 'algorithm_code': 0, 'algorithm_name': 'Unknown'}

    def set_gas(self, gas_number: int):
        """Establece el gas activo para medición de flujo másico"""
        command = self._format_command("set_gas", gas_number=gas_number)
        response = self._send_command(command)
        if response:
            self.logger.info(f"Gas establecido en #{gas_number}")
        return response

    def tare_flow(self):
        """Hace tare del flujo"""
        command = self._format_command("tare_flow")
        response = self._send_command(command)
        if response:
            self.logger.info("Tare de flujo realizado")
        return response

    def tare_pressure(self):
        """Hace tare de la presión"""
        command = self._format_command("tare_gauge_diff_pressure")
        response = self._send_command(command)
        if response:
            self.logger.info("Tare de presión realizado")
        return response

    def lock_display(self):
        """Bloquea la pantalla del dispositivo"""
        command = self._format_command("lock_device_display")
        response = self._send_command(command)
        if response:
            self.logger.info("Pantalla bloqueada")
        return response

    def unlock_display(self):
        """Desbloquea la pantalla del dispositivo"""
        command = self._format_command("unlock_device_display")
        response = self._send_command(command)
        if response:
            self.logger.info("Pantalla desbloqueada")
        return response
    @contextmanager
    def connection(self):
        """Context manager para manejar la conexión serial"""
        try:
            self._connect()
            yield self.serial_conn
        except Exception as e:
            # Re-lanzar excepciones para que sean manejadas por el caller
            raise
        finally:
            self._disconnect()

    def _connect(self):
        """Establece conexión con el controlador Alicat"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=0.01
            )
            time.sleep(2)  # Esperar estabilización
            self.logger.info(f"Conexión establecida con Alicat en puerto {self.port}")

            # Verificar conexión
            if not self._test_connection():
                raise AlicatConnectionError("No se pudo verificar la conexión con Alicat")

        except Exception as e:
            raise AlicatConnectionError(f"Error de conexión serial: {e}")

    def _disconnect(self):
        """Cierra la conexión serial"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            self.logger.info("Conexión con Alicat cerrada")

    def _test_connection(self) -> bool:
        """Prueba la conexión enviando un comando básico"""
        try:
            command = self._format_command("poll_device_data")
            self.serial_conn.write(f'{command}\r'.encode('ascii'))
            time.sleep(0.1)
            response = self.serial_conn.readline().decode('ascii', errors='ignore').strip()
            # Verificar que tenemos una respuesta no vacía
            return bool(response and response.strip())
        except Exception as e:
            self.logger.error(f"Error probando conexión: {e}")
            return False

    def _send_command(self, command: str) -> str:
        """Envía un comando y recibe la respuesta"""
        if not self.serial_conn or not self.serial_conn.is_open:
            raise AlicatConnectionError("Conexión no establecida")

        try:
            # Limpiar buffer
            self.serial_conn.reset_input_buffer()

            # Enviar comando
            cmd_bytes = f"{command}\r".encode('ascii')
            self.serial_conn.write(cmd_bytes)
            self.logger.debug(f"Comando enviado: {command}")

            # Esperar respuesta
            time.sleep(0.1)
            response = self.serial_conn.readline().decode('ascii', errors='ignore').strip()
            self.logger.debug(f"Respuesta recibida: {response.split()}")
            if not response:
                self.logger.warning(f"No se recibió respuesta para comando: {command}")

            return response

        except Exception as e:
            raise AlicatCalibrationError(f"Error enviando comando '{command}': {e}")

    def read_current_values(self) -> Dict[str, float]:
        """
        Lee los valores actuales del controlador
        Returns: Dict con caudal, presión, temperatura (si está disponible)
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self._send_command(self._format_command("poll_device_data"))

                if not response:
                    if attempt < max_retries - 1:
                        self.logger.debug(f"Reintento {attempt + 1} de lectura de valores")
                        time.sleep(0.1)
                        continue
                    raise AlicatCalibrationError("No se pudieron leer valores actuales")

                # Formato típico: "A +000.00 +000.00 +000.00" o "A +000.00 +000.00"
                parts = response.split()

                if len(parts) < 3:
                    if attempt < max_retries - 1:
                        self.logger.debug(f"Respuesta inválida, reintento {attempt + 1}: {response}")
                        time.sleep(0.1)
                        continue
                    raise AlicatCalibrationError(f"Respuesta inválida: {response}")

                result = {
                    'flow_rate': float(parts[1]),  # Caudal
                    'pressure': float(parts[2]) if len(parts) > 2 else 0.0,   # Presión
                    'temperature': float(parts[3]) if len(parts) > 3 else 0.0  # Temperatura
                }
                return result

            except (ValueError, IndexError) as e:
                if attempt < max_retries - 1:
                    self.logger.debug(f"Error parseando respuesta, reintento {attempt + 1}: {e}")
                    time.sleep(0.1)
                    continue
                raise AlicatCalibrationError(f"Error parseando valores: {response} - {e}")

        # Este punto nunca debería alcanzarse, pero por si acaso
        raise AlicatCalibrationError("Error inesperado en lectura de valores")

    def set_setpoint(self, setpoint: float):
        """Establece el setpoint del controlador"""
        if not 0 <= setpoint <= 100:
            raise ValueError("Setpoint debe estar entre 0 y 100")

        command = self._format_command("change_setpoint", setpoint_value=f"{setpoint:.2f}")
        response = self._send_command(command)

        if response:
            self.logger.info(f"Setpoint establecido en {setpoint}")
        else:
            raise AlicatCalibrationError("No se pudo establecer el setpoint")

    def _validate_setpoint(self, setpoint: float):
        """Valida que el setpoint esté en rango válido"""
        if not 0 <= setpoint <= 100:
            raise ValueError("Setpoint debe estar entre 0 y 100")

    def _validate_duration(self, duration: int):
        """Valida que la duración sea razonable"""
        if duration < 10:
            raise ValueError("Duración debe ser al menos 10 segundos")

    def _ensure_output_directory(self, file_path: str):
        """Asegura que el directorio del archivo de salida existe"""
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
            self.logger.info(f"Directorio creado: {directory}")

    def calibrate_pid(self, setpoint: float, duration: int,
                     output_file: Optional[str] = None) -> Dict[str, any]:
        """
        Realiza calibración PID completa

        Args:
            setpoint: Valor objetivo (0-34)
            duration: Duración de la calibración en segundos
            output_file: Archivo CSV para guardar datos (opcional)

        Returns:
            Dict con resultados de la calibración
        """
        self.logger.info(f"Iniciando calibración PID - Setpoint: {setpoint}, Duración: {duration}s")
        
        self.set_setpoint(0.0)  # Asegurar setpoint en 0 al inicio
        time.sleep(5.0)  # Esperar estabilización inicial

        # Validar parámetros
        if not 0 <= setpoint <= 34:
            raise ValueError("Setpoint debe estar entre 0 y 34")
        if duration < 20:
            raise ValueError("Duración debe ser al menos 20 segundos")

        # Leer valores iniciales
        initial_values = self.read_current_values()
        self.logger.info(f"Valores iniciales - Caudal: {initial_values['flow_rate']}, "
                        f"Presión: {initial_values['pressure']}, "
                        f"Temperatura: {initial_values['temperature']}")


        # Preparar archivo CSV si se especifica
        csv_writer = None
        if output_file:
            csv_dir = os.path.dirname(output_file)
            if csv_dir and not os.path.exists(csv_dir):
                os.makedirs(csv_dir)

            csv_file = open(output_file, 'w', newline='')
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(['Timestamp', 'Time_s', 'Flow_Rate', 'Pressure', 'Temperature', 'Setpoint'])

        # Iniciar monitoreo 1 segundo antes del setpoint
        self.logger.info("Iniciando monitoreo de calibración (1s antes del setpoint)...")
        start_time = time.time()
        measurements = []

        # Función para establecer setpoint en thread separado
        def set_setpoint_async():
            time.sleep(1.0)  # Esperar 1 segundo antes de establecer setpoint
            self.logger.info(f"Estableciendo setpoint en {setpoint}")
            self.set_setpoint(setpoint)
            time.sleep(0.5)  # Dar tiempo al dispositivo para procesar el cambio

        # Iniciar thread para establecer setpoint
        setpoint_thread = threading.Thread(target=set_setpoint_async, daemon=True)
        setpoint_thread.start()

        try:
            while (time.time() - start_time) < duration:
                current_time = time.time() - start_time
                try:
                    values = self.read_current_values()
                except AlicatCalibrationError as e:
                    self.logger.warning(f"Error leyendo valores en {current_time:.1f}s: {e}")
                    # Usar valores por defecto o del último measurement válido
                    if measurements:
                        values = measurements[-1].copy()
                        values.pop('timestamp', None)
                        values.pop('time_s', None)
                        values.pop('setpoint', None)
                    else:
                        values = {'flow_rate': 0.0, 'pressure': 0.0, 'temperature': 0.0}
                    self.logger.info(f"Usando valores alternativos: {values}")

                measurement = {
                    'timestamp': datetime.now().isoformat(),
                    'time_s': current_time,
                    'flow_rate': values['flow_rate'],
                    'pressure': values['pressure'],
                    'temperature': values['temperature'],
                    'setpoint': setpoint
                }

                measurements.append(measurement)

                # Guardar en CSV si está habilitado
                if csv_writer:
                    csv_writer.writerow([
                        measurement['timestamp'],
                        measurement['time_s'],
                        measurement['flow_rate'],
                        measurement['pressure'],
                        measurement['temperature'],
                        measurement['setpoint']
                    ])

                # # Log cada 5 segundos
                # if int(current_time) % 5 == 0 and current_time > 0:
                #     self.logger.info(f"Calibración en progreso: {current_time:.1f}s - Caudal: {values['flow_rate']:.2f}")

                time.sleep(0.4)  # Muestreo cada 0.5 segundos

        except KeyboardInterrupt:
            self.logger.warning("Calibración interrumpida por usuario")
        except Exception as e:
            self.logger.error(f"Error durante calibración: {e}")
            raise
        finally:
            # Esperar que el thread del setpoint termine
            setpoint_thread.join(timeout=2.0)
            if csv_writer:
                csv_file.close()

        # Calcular estadísticas finales
        final_values = self.read_current_values()
        stability_time = self._calculate_stability_time(measurements, setpoint)

        results = {
            'setpoint': setpoint,
            'duration': duration,
            'initial_values': initial_values,
            'final_values': final_values,
            'measurements': measurements,
            'stability_time': stability_time,
            'output_file': output_file,
            'total_measurements': len(measurements)
        }

        self.logger.info("Calibración PID completada exitosamente")
        self.logger.info(f"Setpoint: {setpoint}, Duración: {duration}s")
        self.logger.info(f"Tiempo de estabilización: {stability_time:.2f}s")
        return results

    def _calculate_stability_time(self, measurements: List[Dict], setpoint: float) -> float:
        """Calcula el tiempo que tomó estabilizarse en el setpoint"""
        if not measurements:
            return 0.0

        # Considerar estabilizado cuando el error es < 1% del setpoint por 10 segundos
        stability_threshold = abs(setpoint * 0.01)
        stability_window = 20  # 10 segundos (20 * 0.5s)

        for i in range(len(measurements) - stability_window):
            window = measurements[i:i + stability_window]
            errors = [abs(m['flow_rate'] - setpoint) for m in window]

            if all(error <= stability_threshold for error in errors):
                return measurements[i]['time_s']

        return measurements[-1]['time_s']  # No se estabilizó


    def get_unit_id_info(self) -> Dict[str, str]:
        """
        Consulta la información del Unit ID del dispositivo Alicat
        Returns: Dict con unit_id, p_gain, d_gain
        """
        try:
            response = self._send_command(self._format_command("query_unit_id"))

            if not response:
                raise AlicatCalibrationError("No se recibió respuesta del comando query_unit_id")

            # El formato típico de respuesta es: 'A', '-00.000', '+00.000'
            # Donde los valores son: Unit ID, Absolute pressure, Temperature
            parts = response.split()
            print (parts)
            if len(parts) < 2:
                raise AlicatCalibrationError(f"Respuesta inválida para unit_id: {response}")

            try:
                unit_id = parts[0]
                absolute_pressure = parts[1]
                temperature = parts[2]


                return {
                    'unit_id': unit_id,
                    'absolute_pressure': absolute_pressure,
                    'temperature': temperature,
                }

            except (ValueError, IndexError) as e:
                raise AlicatCalibrationError(f"Error parseando respuesta unit_id: {e}")

        except Exception as e:
            raise AlicatCalibrationError(f"Error consultando unit_id: {e}")

    def set_loop_control_algorithm(self, algorithm: str):
        """
        Establece el algoritmo de control de lazo (LCA) del dispositivo Alicat
        Args:
            algorithm: 'PD/PDF' o 'PD2I'
        """
        algorithm_map = {
            'PD/PDF': 1,
            'PD2I': 2
        }

        if algorithm not in algorithm_map:
            raise ValueError("Algoritmo inválido. Use 'PD/PDF' o 'PD2I'.")

        algorithm_code = algorithm_map[algorithm]

        try:
            response = self._send_command(self._format_command("loop_control_algorithm", algorithm=algorithm_code))

            if not response:
                raise AlicatCalibrationError("No se recibió respuesta del comando loop_control_algorithm")

            # Verificar que el comando fue exitoso
            if not response.startswith('A'):
                raise AlicatCalibrationError(f"Error estableciendo LCA: {response}")

            self.logger.info(f"Algoritmo de control de lazo establecido en {algorithm} ({algorithm_code})")
            return response

        except Exception as e:
            raise AlicatCalibrationError(f"Error estableciendo LCA: {e}")

    def get_loop_control_algorithm(self) -> Dict[str, str]:
        """
        Consulta el algoritmo de control de lazo (LCA) del dispositivo Alicat
        Returns: Dict con algorithm y description
        """
        try:
            response = self._send_command(self._format_command("query_loop_algorithm"))
            print(response)

            if not response:
                raise AlicatCalibrationError("No se recibió respuesta del comando query_loop_algorithm")

            # El formato típico de respuesta es: "A 1" o "A 2"
            # Donde 1 = PD/PDF, 2 = PD2I
            parts = response.split()

            if len(parts) < 2:
                raise AlicatCalibrationError(f"Respuesta inválida para LCA: {response}")

            try:
                algorithm_code = int(parts[1])

                if algorithm_code == 1:
                    algorithm = "PD/PDF"
                    description = "Proportional-Derivative / Proportional-Derivative-Filtered"
                elif algorithm_code == 2:
                    algorithm = "PD2I"
                    description = "Proportional-Derivative 2-Integral"
                else:
                    algorithm = f"Unknown ({algorithm_code})"
                    description = "Algoritmo desconocido"

                return {
                    'algorithm': algorithm,
                    'description': description,
                    'code': algorithm_code
                }

            except (ValueError, IndexError) as e:
                raise AlicatCalibrationError(f"Error parseando respuesta LCA: {e}")

        except Exception as e:
            raise AlicatCalibrationError(f"Error consultando LCA: {e}")


    def set_pid_gains(self, p_gain: int, i_gain: Optional[int] = None, d_gain: int = 0):
        """
        Establece las ganancias PID del dispositivo Alicat
        Args:
            p_gain: Ganancia proporcional 0 - 65,535
            i_gain: Ganancia integral (si aplica) 0 - 65,535
            d_gain: Ganancia derivativa 0 - 65,535
        Returns: Respuesta del comando
            Successful command response: the device responds with 
            the unit ID followed by the current P, I, and D gains and the 
            number 0. The number 0 does not currently signify anything 
            and is there to reserve a position within the command for 
            any future functions.
        """
        try:
            # Primero determinar el algoritmo LCA
            lca_info = self.get_loop_control_algorithm()
            algorithm_code = lca_info.get('code', 0)
            if algorithm_code == 1:
                # PD/PDF algorithm - establecer ganancias P y D
                response = self._send_command(self._format_command(
                    "pd_pdf_gains",
                    save=1,
                    p_gain=f"{p_gain}",
                    d_gain=f"{d_gain}"
                ))

                if not response:
                    raise AlicatCalibrationError("No se recibió respuesta del comando pd_pdf_gains")

                # Verificar que el comando fue exitoso
                if not response.startswith('A'):
                    raise AlicatCalibrationError(f"Error estableciendo PD/PDF gains: {response}")

                self.logger.info(f"Ganancias PD/PDF establecidas - P: {p_gain}, D: {d_gain}")
                return response

            elif algorithm_code == 2:
                # PD2I algorithm - establecer ganancias P, I y D
                if i_gain is None:
                    raise ValueError("i_gain es requerido para el algoritmo PD2I")

                response = self._send_command(self._format_command(
                    "pd2i_gains",
                    save=1,
                    p_gain=f"{p_gain}",
                    i_gain=f"{i_gain}",
                    d_gain=f"{d_gain}"
                ))

                if not response:
                    raise AlicatCalibrationError("No se recibió respuesta del comando pd2i_gains")

                # Verificar que el comando fue exitoso
                if not response.startswith('A'):
                    raise AlicatCalibrationError(f"Error estableciendo PD2I gains: {response}")

                self.logger.info(f"Ganancias PD2I establecidas - P: {p_gain}, I: {i_gain}, D: {d_gain}")
                return response

            else:
                raise AlicatCalibrationError(f"Algoritmo LCA desconocido: {algorithm_code}")

        except Exception as e:
            raise AlicatCalibrationError(f"Error estableciendo ganancias PID: {e}")

    def get_pid_gains(self) -> Dict[str, str]:
        """
        Consulta las ganancias PID del dispositivo Alicat
        Returns: Dict con p_gain, i_gain (si aplica), d_gain y algorithm
        """
        try:
            # Primero determinar el algoritmo LCA
            lca_info = self.get_loop_control_algorithm()
            algorithm_code = lca_info.get('code', 0)

            if algorithm_code == 1:
                # PD/PDF algorithm - consultar ganancias P y D
                response = self._send_command(self._format_command("read_pd_pdf_gains"))

                if not response:
                    raise AlicatCalibrationError("No se recibió respuesta del comando read_pd_pdf_gains")

                # El formato típico de respuesta es: "A +000.00 +000.00"
                # Donde los valores son: P Gain, D Gain
                parts = response.split()

                if len(parts) < 3:
                    raise AlicatCalibrationError(f"Respuesta inválida para PD/PDF gains: {response}")

                try:
                    p_gain = parts[1]
                    d_gain = parts[2]

                    return {
                        'algorithm': 'PD/PDF',
                        'p_gain': p_gain,
                        'i_gain': 'N/A',
                        'd_gain': d_gain
                    }

                except (ValueError, IndexError) as e:
                    raise AlicatCalibrationError(f"Error parseando respuesta PD/PDF gains: {e}")

            elif algorithm_code == 2:
                # PD2I algorithm - consultar ganancias P, I y D
                response = self._send_command(self._format_command("read_pd2i_gains"))

                if not response:
                    raise AlicatCalibrationError("No se recibió respuesta del comando read_pd2i_gains")

                # El formato típico de respuesta es: "A +000.00 +000.00 +000.00"
                # Donde los valores son: P Gain, I Gain, D Gain
                parts = response.split()

                if len(parts) < 4:
                    raise AlicatCalibrationError(f"Respuesta inválida para PD2I gains: {response}")

                try:
                    p_gain = parts[1]
                    i_gain = parts[2]
                    d_gain = parts[3]

                    return {
                        'algorithm': 'PD2I',
                        'p_gain': p_gain,
                        'i_gain': i_gain,
                        'd_gain': d_gain
                    }

                except (ValueError, IndexError) as e:
                    raise AlicatCalibrationError(f"Error parseando respuesta PD2I gains: {e}")

            else:
                raise AlicatCalibrationError(f"Algoritmo LCA desconocido: {algorithm_code}")

        except Exception as e:
            raise AlicatCalibrationError(f"Error consultando ganancias PID: {e}")

    def get_baud_rate(self) -> int:
        """
        Consulta la tasa de baudios del dispositivo Alicat
        Returns: Tasa de baudios (int)
        """
        try:
            response = self._send_command(self._format_command("baud_rate_settings", new_baud_rate= ''))

            if not response:
                raise AlicatCalibrationError("No se recibió respuesta del comando NCB")

            # El formato típico de respuesta es: "A 9600"
            parts = response.split()

            if len(parts) < 2:
                raise AlicatCalibrationError(f"Respuesta inválida para baud rate: {response}")

            try:
                baud_rate = int(parts[1])
                return baud_rate

            except (ValueError, IndexError) as e:
                raise AlicatCalibrationError(f"Error parseando respuesta baud rate: {e}")

        except Exception as e:
            raise AlicatCalibrationError(f"Error consultando baud rate: {e}")

    def set_baud_rate(self, baud_rate: int):
        """
        Establece la tasa de baudios del dispositivo Alicat
        Args:
            baud_rate: Nueva tasa de baudios (int)
        Returns: Respuesta del comando
        """
        valid_baud_rates = [2400, 9600, 19200, 38400, 57600, 115200]
        if baud_rate not in valid_baud_rates:
            raise ValueError(f"Baud rate inválido. Valores válidos: {valid_baud_rates}")

        try:
            response = self._send_command(self._format_command("baud_rate_settings", new_baud_rate=baud_rate))

            if not response:
                raise AlicatCalibrationError("No se recibió respuesta del comando NCB")

            # Verificar que el comando fue exitoso
            if not response.startswith('A'):
                raise AlicatCalibrationError(f"Error estableciendo baud rate: {response}")

            self.logger.info(f"Baud rate establecido en {baud_rate}")
            return response

        except Exception as e:
            raise AlicatCalibrationError(f"Error estableciendo baud rate: {e}")

    def restore_factory_settings(self):
        """
        Restaura los ajustes de fábrica del dispositivo Alicat
        Returns: Respuesta del comando
        """
        try:
            response = self._send_command(self._format_command("restore_factory_settings"))

            if not response:
                raise AlicatCalibrationError("No se recibió respuesta del comando FACTORY RESTORE ALL")

            # Verificar que el comando fue exitoso
            if not response.startswith('A'):
                raise AlicatCalibrationError(f"Error restaurando ajustes de fábrica: {response}")

            self.logger.info("Ajustes de fábrica restaurados exitosamente")
            return response

        except Exception as e:
            raise AlicatCalibrationError(f"Error restaurando ajustes de fábrica: {e}")

def main():
    """Función principal para demostración"""
    print("🏭 Sistema de Calibración PID Alicat")
    print("=" * 40)

    # Configurar controlador
    alicat = AlicatController(port="COM5")

    try:
        with alicat.connection():
            # Configurar archivo de salida

            firmware = alicat.get_firmware_version()
            manufacturing_info = alicat.get_manufacturing_info()

            print(f"Versión del firmware: {firmware}")
            print(f"Información de manufactura: {manufacturing_info}")
            pd2i_gains = alicat._send_command(alicat._format_command("read_pd2i_gains"))
            loop_control_algorithm_r = alicat._send_command("A LCA")
            print(f"Algoritmo de control de lazo: {loop_control_algorithm_r}")
            print(f"Ganancias PD2I actuales: {pd2i_gains}")
            # # Barrido de presiones para calibración de pid rango de 0-6.5
            # press = np.arange(0.5, 6.5 + 0.01, 0.5)  # +0.01 to include 6.5
            # for p in press:
            #     timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            #     output_file = f"calibration_data/calibration_pid_{p}_pressure.csv"
            #     print(f"Calibrando PID a presión: {p}")
            #     results = alicat.calibrate_pid(
            #         setpoint=p,
            #         duration=20,
            #         output_file=output_file
            #     )
            #     alicat.set_setpoint(0)
            print("✅ Calibración completada exitosamente")


    except AlicatPIDError as e:
        print(f"❌ Error del sistema Alicat: {e}")
        return 1
    except KeyboardInterrupt:   
        print("\n🛑 Calibración interrumpida por usuario")
        return 1
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())