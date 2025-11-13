# Módulo de Respuesta a Pulso Único

Este módulo implementa una rutina sincronizada entre el controlador Alicat y el multímetro Keithley para caracterizar la respuesta del sistema a un pulso de presión escalón.

## Descripción de la Rutina

La rutina ejecuta la siguiente secuencia automáticamente:

1. **Inicialización**: Configura Alicat (setpoint inicial 0 kPa) y Keithley (adquisición rápida)
2. **Adquisición Continua**: Inicia adquisición indefinida de Keithley (1000 muestras/bloque, NPLC=0.001)
3. **Pulso de Presión**: Alicat cambia de 0 kPa → 1 kPa
4. **Monitoreo de Estabilidad**: Espera hasta que la tensión del Keithley se estabilice por 10 segundos
5. **Retorno a Baseline**: Alicat vuelve a 0 kPa
6. **Estabilidad Final**: Espera otros 10 segundos de estabilidad en la tensión
7. **Finalización**: Detiene la adquisición y guarda resultados

## Parámetros de Configuración

### Keithley
- **NPLC**: 0.001 (máxima velocidad)
- **Muestras por bloque**: 1000
- **Modo**: Infinito (hasta condición de parada)
- **Archivo de salida**: `lecturas/dc_voltage_readings_single_pulse_response_YYYYMMDD_HHMMSS.csv`

### Alicat
- **Setpoint inicial**: 0 kPa
- **Setpoint de pulso**: 1 kPa
- **Puerto**: COM5 (configurable)

### Criterios de Estabilidad
- **Threshold de variación**: 0.1 mV máximo
- **Ventana de estabilidad**: 10 segundos
- **Ventana final**: 10 segundos

## Uso del Módulo

### Uso Básico

```python
from response_single_pulse import SinglePulseResponse

# Crear instancia de la rutina
routine = SinglePulseResponse(alicat_port="COM5")

# Inicializar instrumentos
if routine.initialize_instruments():
    # Ejecutar rutina completa
    results = routine.run_single_pulse_routine()

    # Verificar resultados
    if results['error']:
        print(f"Error: {results['error']}")
    else:
        print("✅ Rutina completada exitosamente")
        print(f"📊 Duración total: {results['total_duration']:.2f} segundos")
        print(f"💾 Datos guardados en: {results['keithley_data_file']}")
else:
    print("❌ Error inicializando instrumentos")
```

### Configuración Avanzada

```python
from response_single_pulse import SinglePulseResponse

# Configuración personalizada del Keithley
keithley_config = {
    'nplc_cycles': 0.001,
    'samples_per_count': 1000,
    'infinite_mode': True,
    'experiment_label': 'mi_experimento',
    'output_dir': 'mis_datos',
    'quiet': True
}

# Configuración personalizada de estabilidad
routine = SinglePulseResponse(
    alicat_port="COM5",
    keithley_config=keithley_config
)

# Personalizar criterios de estabilidad
routine.stability_threshold_voltage = 0.00005  # 0.05 mV
routine.stability_window_seconds = 15.0        # 15 segundos
routine.final_stability_window_seconds = 15.0  # 15 segundos

# Personalizar setpoints
routine.initial_setpoint = 0.0  # kPa
routine.pulse_setpoint = 2.0   # kPa (cambiar si es necesario)
```

### Ejecución desde Línea de Comandos

```bash
cd /ruta/al/proyecto
python response_single_pulse.py
```

## Resultados

La rutina retorna un diccionario con los siguientes resultados:

```python
{
    'pulse_start_time': timestamp_cuando_inicia_pulso,
    'stability_achieved_time': timestamp_cuando_estabiliza_despues_pulso,
    'pulse_end_time': timestamp_cuando_vuelve_a_0_kPa,
    'final_stability_time': timestamp_cuando_estabiliza_finalmente,
    'total_duration': duracion_total_segundos,
    'keithley_data_file': ruta_al_archivo_csv,
    'error': mensaje_de_error_si_ocurre
}
```

## Archivos Generados

1. **Datos de Keithley**: CSV con todas las mediciones de tensión
2. **Log de la rutina**: Archivo de log con eventos detallados
3. **Resultados**: Información de timestamps y duración

## Requisitos

- Python 3.8+
- Módulos: `alicat_pid_calibration.py`, `acquisition.py`
- Instrumentos: Controlador Alicat, Multímetro Keithley
- Puertos seriales configurados correctamente

## Manejo de Errores

El módulo incluye manejo robusto de errores:
- Validación de conexiones de instrumentos
- Recuperación de errores durante adquisición
- Logging detallado para debugging
- Limpieza automática de recursos

## Notas Técnicas

- La estabilidad se determina por variación máxima de tensión en ventana deslizante
- Los datos del Keithley se monitorean en tiempo real leyendo el archivo CSV
- La rutina usa threading para monitoreo concurrente
- Todos los timestamps usan tiempo Unix de alta precisión