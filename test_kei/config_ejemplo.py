# Archivo de configuración para main_acquisition.py
# Modifica estos valores según tus necesidades experimentales

# =============================================================================
# CONFIGURACIÓN DEL KEITHLEY
# =============================================================================

KEITHLEY_CONFIG = {
    # Directorio donde se guardarán los datos
    'output_dir': 'lecturas',

    # Etiqueta identificadora del experimento
    'experiment_label': 'experimento_presion',

    # Ciclos NPLC (Number of Power Line Cycles)
    # Mayor valor = mayor precisión pero más lento
    # Valores típicos: 0.01, 0.1, 1, 10
    'nplc_cycles': 0.001,

    # Número de muestras por bloque de adquisición
    # Mayor valor = más datos pero más tiempo
    'samples_per_count': 1000,

    # Modo de adquisición
    # False = número finito de bloques, True = adquisición infinita
    'infinite_mode': False,

    # Número de bloques (solo si infinite_mode = False)
    'num_blocks': 50,

    # Mostrar prompts de confirmación
    'quiet': False
}

# =============================================================================
# CONFIGURACIÓN DE PARÁMETROS DE ADQUISICIÓN
# =============================================================================

ACQUISITION_PARAMS = {
    # Presión inicial del experimento (kPa)
    'setpoint_inicial': 0.0,

    # Presión final del experimento (kPa)
    'setpoint_final': 6.86,

    # Tiempo entre cambios de setpoint (segundos)
    # Tiempo que permanece en cada presión antes de cambiar
    'setpoint_intervalo': 30.0,

    # Número de puntos intermedios en cada rampa
    # Solo aplica en modo 'auto'
    'num_puntos_intermedios': 5,

    # Número de ciclos completos (subida + bajada)
    'num_ciclos': 2,

    # Modo de puntos intermedios
    # 'auto': genera puntos automáticamente
    # 'manual': usa lista personalizada
    'intermediate_mode': 'auto',

    # Lista de puntos personalizados (solo si intermediate_mode = 'manual')
    # Formato: cadena que representa una lista de Python
    'custom_points_text': '[0, 1.5, 3.0, 4.5, 6.86]',

    # Habilitar estabilización de presión
    # True: espera a que la presión se estabilice antes de adquirir datos
    # False: cambia inmediatamente al siguiente setpoint
    'enable_stability': True,

    # Tiempo máximo para estabilizar la presión (segundos)
    # Solo aplica si enable_stability = True
    'stability_time': 15.0,

    # Prefijo para los archivos CSV generados
    'file_label': 'ExperimentoPresion'
}

# =============================================================================
# CONFIGURACIÓN DE EJECUCIÓN
# =============================================================================

EXECUTION_CONFIG = {
    # Probar conexiones con instrumentos antes de iniciar
    'test_connections': True,

    # Nivel de logging
    # DEBUG, INFO, WARNING, ERROR
    'log_level': 'INFO',

    # Archivo para guardar logs (opcional)
    # None = solo mostrar en consola
    'log_file': None
}

# =============================================================================
# CONFIGURACIONES PREDEFINIDAS PARA DIFERENTES EXPERIMENTOS
# =============================================================================

# Configuración para experimento rápido (desarrollo/pruebas)
CONFIG_RAPIDO = {
    'keithley': {
        'output_dir': 'datos_prueba',
        'experiment_label': 'prueba_rapida',
        'nplc_cycles': 1,
        'samples_per_count': 100,
        'infinite_mode': False,
        'num_blocks': 5,
        'quiet': False
    },
    'acquisition': {
        'setpoint_inicial': 0.0,
        'setpoint_final': 2.0,
        'setpoint_intervalo': 5.0,
        'num_puntos_intermedios': 2,
        'num_ciclos': 1,
        'intermediate_mode': 'auto',
        'custom_points_text': '[0, 1.0, 2.0]',
        'enable_stability': False,
        'stability_time': 5.0,
        'file_label': 'PruebaRapida'
    },
    'execution': {
        'test_connections': True,
        'log_level': 'DEBUG',
        'log_file': 'prueba_rapida.log'
    }
}

# Configuración para experimento de alta precisión
CONFIG_ALTA_PRECISION = {
    'keithley': {
        'output_dir': 'datos_precision',
        'experiment_label': 'alta_precision',
        'nplc_cycles': 20,
        'samples_per_count': 2000,
        'infinite_mode': False,
        'num_blocks': 100,
        'quiet': False
    },
    'acquisition': {
        'setpoint_inicial': 0.0,
        'setpoint_final': 8.0,
        'setpoint_intervalo': 60.0,
        'num_puntos_intermedios': 8,
        'num_ciclos': 3,
        'intermediate_mode': 'auto',
        'custom_points_text': '[0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]',
        'enable_stability': True,
        'stability_time': 30.0,
        'file_label': 'AltaPrecision'
    },
    'execution': {
        'test_connections': True,
        'log_level': 'INFO',
        'log_file': 'alta_precision.log'
    }
}

# Configuración para monitoreo continuo
CONFIG_MONITOREO = {
    'keithley': {
        'output_dir': 'datos_monitoreo',
        'experiment_label': 'monitoreo_continuo',
        'nplc_cycles': 5,
        'samples_per_count': 500,
        'infinite_mode': True,  # Modo infinito
        'num_blocks': 50,  # No aplica en modo infinito
        'quiet': False
    },
    'acquisition': {
        'setpoint_inicial': 4.0,  # Presión constante
        'setpoint_final': 4.0,    # Misma presión
        'setpoint_intervalo': 10.0,
        'num_puntos_intermedios': 0,
        'num_ciclos': 1,
        'intermediate_mode': 'auto',
        'custom_points_text': '[4.0]',
        'enable_stability': True,
        'stability_time': 10.0,
        'file_label': 'MonitoreoPresion'
    },
    'execution': {
        'test_connections': True,
        'log_level': 'INFO',
        'log_file': 'monitoreo.log'
    }
}

# Configuración para caracterización de histéresis
CONFIG_HISTERESIS = {
    'keithley': {
        'output_dir': 'datos_histeresis',
        'experiment_label': 'caracterizacion_histeresis',
        'nplc_cycles': 10,
        'samples_per_count': 1500,
        'infinite_mode': False,
        'num_blocks': 75,
        'quiet': False
    },
    'acquisition': {
        'setpoint_inicial': 0.0,
        'setpoint_final': 7.0,
        'setpoint_intervalo': 45.0,
        'num_puntos_intermedios': 7,
        'num_ciclos': 5,  # Múltiples ciclos para histéresis
        'intermediate_mode': 'auto',
        'custom_points_text': '[0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]',
        'enable_stability': True,
        'stability_time': 20.0,
        'file_label': 'Histeresis'
    },
    'execution': {
        'test_connections': True,
        'log_level': 'INFO',
        'log_file': 'histeresis.log'
    }
}

# =============================================================================
# FUNCIONES DE CARGA DE CONFIGURACIÓN
# =============================================================================

def load_config(config_name=None):
    """
    Carga una configuración predefinida

    Args:
        config_name: Nombre de la configuración ('rapido', 'precision', 'monitoreo', 'histeresis')
                    Si None, retorna la configuración por defecto

    Returns:
        tuple: (keithley_config, acquisition_params, execution_config)
    """
    if config_name is None:
        return KEITHLEY_CONFIG, ACQUISITION_PARAMS, EXECUTION_CONFIG

    config_name = config_name.lower()

    if config_name == 'rapido':
        config = CONFIG_RAPIDO
    elif config_name == 'precision':
        config = CONFIG_ALTA_PRECISION
    elif config_name == 'monitoreo':
        config = CONFIG_MONITOREO
    elif config_name == 'histeresis':
        config = CONFIG_HISTERESIS
    else:
        raise ValueError(f"Configuración '{config_name}' no encontrada. Opciones: rapido, precision, monitoreo, histeresis")

    return config['keithley'], config['acquisition'], config['execution']

def save_config_to_file(filename="mi_config.py"):
    """
    Guarda la configuración actual en un archivo Python

    Args:
        filename: Nombre del archivo donde guardar
    """
    import json

    config_content = f'''# Configuración personalizada generada automáticamente
# Archivo: {filename}
# Fecha: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

KEITHLEY_CONFIG = {json.dumps(KEITHLEY_CONFIG, indent=4)}

ACQUISITION_PARAMS = {json.dumps(ACQUISITION_PARAMS, indent=4)}

EXECUTION_CONFIG = {json.dumps(EXECUTION_CONFIG, indent=4)}
'''

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(config_content)

    print(f"✅ Configuración guardada en {filename}")

# =============================================================================
# VALIDACIÓN DE CONFIGURACIÓN
# =============================================================================

def validate_config(keithley_config, acquisition_params):
    """
    Valida una configuración completa

    Args:
        keithley_config: Configuración del Keithley
        acquisition_params: Parámetros de adquisición

    Returns:
        list: Lista de errores encontrados (vacía si válida)
    """
    errors = []

    # Validar Keithley
    required_keithley = ['output_dir', 'experiment_label', 'nplc_cycles',
                        'samples_per_count', 'infinite_mode', 'quiet']
    for key in required_keithley:
        if key not in keithley_config:
            errors.append(f"Falta clave requerida en KEITHLEY_CONFIG: {key}")

    if keithley_config.get('nplc_cycles', 0) <= 0:
        errors.append("KEITHLEY_CONFIG['nplc_cycles'] debe ser mayor que 0")

    if keithley_config.get('samples_per_count', 0) <= 0:
        errors.append("KEITHLEY_CONFIG['samples_per_count'] debe ser mayor que 0")

    # Validar adquisición
    required_acq = ['setpoint_inicial', 'setpoint_final', 'setpoint_intervalo',
                   'num_puntos_intermedios', 'num_ciclos', 'intermediate_mode']
    for key in required_acq:
        if key not in acquisition_params:
            errors.append(f"Falta clave requerida en ACQUISITION_PARAMS: {key}")

    if acquisition_params.get('setpoint_inicial', 0) < 0:
        errors.append("ACQUISITION_PARAMS['setpoint_inicial'] no puede ser negativo")

    if acquisition_params.get('setpoint_final', 0) < 0:
        errors.append("ACQUISITION_PARAMS['setpoint_final'] no puede ser negativo")

    if acquisition_params.get('setpoint_intervalo', 0) <= 0:
        errors.append("ACQUISITION_PARAMS['setpoint_intervalo'] debe ser mayor que 0")

    if acquisition_params.get('num_ciclos', 0) <= 0:
        errors.append("ACQUISITION_PARAMS['num_ciclos'] debe ser mayor que 0")

    if acquisition_params.get('intermediate_mode') not in ['auto', 'manual']:
        errors.append("ACQUISITION_PARAMS['intermediate_mode'] debe ser 'auto' o 'manual'")

    return errors

# =============================================================================
# EJEMPLO DE USO
# =============================================================================

if __name__ == "__main__":
    # Ejemplo de validación
    errors = validate_config(KEITHLEY_CONFIG, ACQUISITION_PARAMS)
    if errors:
        print("❌ Errores de configuración encontrados:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("✅ Configuración válida")

    # Ejemplo de carga de configuración predefinida
    try:
        k_config, a_params, e_config = load_config('rapido')
        print("✅ Configuración 'rapido' cargada exitosamente")
    except ValueError as e:
        print(f"❌ Error cargando configuración: {e}")

    # Guardar configuración actual
    # save_config_to_file("mi_config_personalizada.py")