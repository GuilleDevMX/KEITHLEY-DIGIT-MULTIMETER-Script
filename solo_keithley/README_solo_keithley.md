# Módulo Keithley Acquisition (solo_keithley.py)

Este módulo proporciona una interfaz completa para adquirir datos del multímetro digital Keithley usando Python y PyVISA.

## Requisitos

- Python 3.7+
- PyVISA
- Controlador VISA (NI-VISA recomendado)
- Instrumento Keithley conectado vía GPIB, USB o Ethernet

## Instalación de dependencias

```bash
pip install pyvisa pyvisa-py
```

Para NI-VISA (recomendado):
- Descargar e instalar NI-VISA desde el sitio web de National Instruments

## Uso básico

### 1. Importar el módulo

```python
from solo_keithley import KeithleyAcquisition
```

### 2. Configurar la adquisición

```python
config = {
    'output_dir': 'lecturas',           # Directorio para datos
    'experiment_label': 'mi_experimento', # Nombre del experimento
    'nplc_cycles': 1,                  # Ciclos NPLC (precisión)
    'samples_per_count': 10,           # Muestras por bloque
    'num_blocks': 5,                   # Número de bloques
    'infinite_mode': False,            # Modo finito/infinito
    'quiet': False                     # Mostrar prompts
}
```

### 3. Crear instancia y ejecutar

```python
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)

# Crear adquisidor
keithley = KeithleyAcquisition(config)

# Ejecutar adquisición
results = keithley.run_acquisition()

# Verificar resultados
if results['error']:
    print(f"Error: {results['error']}")
else:
    print(f"Adquisición exitosa: {results['total_samples']} muestras")
    print(f"Archivo: {results['csv_file']}")
```

## Parámetros de configuración

### Parámetros principales

- **`output_dir`**: Directorio donde se guardarán los archivos CSV
- **`experiment_label`**: Etiqueta para identificar el experimento
- **`nplc_cycles`**: Ciclos NPLC (Number of Power Line Cycles)
  - `0.001`: Muy alta precisión (muy lento)
  - `1`: Precisión estándar
  - `10`: Baja precisión (rápido)
- **`samples_per_count`**: Número de muestras por bloque
- **`num_blocks`**: Número de bloques a adquirir (ignorado en modo infinito)
- **`infinite_mode`**: `True` para adquisición continua hasta interrupción
- **`quiet`**: `True` para modo silencioso sin prompts

### Configuraciones recomendadas

#### Alta precisión (lento)
```python
config = {
    'nplc_cycles': 10,
    'samples_per_count': 1,
    'num_blocks': 100
}
```

#### Alta velocidad (menos preciso)
```python
config = {
    'nplc_cycles': 0.1,
    'samples_per_count': 100,
    'num_blocks': 10
}
```

#### Adquisición continua
```python
config = {
    'infinite_mode': True,
    'nplc_cycles': 1,
    'samples_per_count': 10
}
```

## Archivo de salida

El módulo genera un archivo CSV con las siguientes columnas:

```
Block, Sample_In_Block, Global_Sample, Voltage_V, Timestamp
1, 1, 1, 1.234567, 2025-11-18T10:30:45.123456
1, 2, 2, 1.234569, 2025-11-18T10:30:45.223456
...
```

## Interrupción manual

Durante la adquisición, puedes presionar:
- `'q'` o `'ESC'` para detener la adquisición
- `Ctrl+C` para interrupción forzada

## Manejo de errores

El módulo incluye manejo completo de errores:

- `KeithleyConnectionError`: Problemas de conexión con el instrumento
- `KeithleyAcquisitionError`: Errores durante la medición

## Logging

El módulo utiliza el sistema de logging de Python. Configura el nivel deseado:

```python
import logging
logging.basicConfig(level=logging.DEBUG)  # Para máxima verbosidad
```

## Ejemplo completo

Ver `ejemplo_uso_keithley.py` para un ejemplo completo de uso.

### Ejecutar ejemplo

```bash
# Adquisición básica
python ejemplo_uso_keithley.py

# Ver ejemplos de configuración
python ejemplo_uso_keithley.py --examples
```

## Dependencias opcionales

- **NumPy**: Para cálculos estadísticos avanzados
- **keyboard**: Para interrupción manual por teclado

Si no están disponibles, algunas funciones estarán limitadas pero el módulo funcionará.

## Solución de problemas

### "No se encontraron instrumentos conectados"
- Verificar que el Keithley esté encendido y conectado
- Verificar instalación de VISA
- Verificar configuración GPIB/USB

### "Timeout en medición"
- Aumentar `nplc_cycles` para mediciones más lentas
- Verificar configuración del instrumento

### "Error de conexión"
- Verificar puerto/cable de conexión
- Reiniciar el instrumento
- Verificar configuración de red (si aplica)

## Soporte

Para problemas específicos del hardware Keithley, consultar el manual del instrumento.