# Sistema de Adquisición de Datos Keithley

Un sistema completo y modular para adquisición de datos de voltaje DC usando instrumentos Keithley, con análisis estadístico avanzado y visualización de datos.

## 🚀 Características

- **Adquisición modular**: Sistema dividido en módulos independientes para fácil mantenimiento
- **Análisis estadístico completo**: Estadísticas descriptivas, autocorrelación, análisis de estabilidad
- **Visualización avanzada**: Gráficas de series temporales, distribuciones, análisis por bloques
- **Configuración flexible**: Argumentos de línea de comandos y archivos de configuración
- **Manejo de errores robusto**: Excepciones personalizadas y logging detallado
- **Interrupción controlada**: Soporte para interrupción manual durante adquisición
- **Tests unitarios**: Cobertura completa con pytest

## 📋 Requisitos del Sistema

- **Python**: 3.8 o superior
- **Instrumento**: Keithley con interfaz USBTMC (compatible con PyVISA)
- **SO**: Windows, Linux, o macOS

## 📦 Instalación

1. **Clona o descarga** los archivos del proyecto
2. **Instala las dependencias**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Instala NI-VISA** (recomendado para mejor soporte USBTMC):
   - Descarga desde: https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html

## 🏗️ Estructura del Proyecto

```
keithley-acquisition/
├── main.py                 # Script original (legacy)
├── main_refactored.py      # Script principal modular
├── gui_interface.py        # 🆕 Interfaz gráfica avanzada
├── config.py              # Configuración y validación
├── acquisition.py         # Lógica de adquisición de datos
├── analysis.py            # Análisis estadístico
├── plotting.py            # Generación de gráficas
├── alicat_pid_calibration.py # Calibración PID Alicat
├── acquisition_instruments.py # Sistema integrado multi-dispositivo
├── test_main.py           # Tests unitarios
├── requirements.txt       # Dependencias actualizadas
├── README.md             # Documentación completa
└── output/               # 📁 Archivos generados
    ├── Datos_20251015_121501.csv    # Datos de adquisición
    ├── voltage_analysis_*.png       # Gráficas de análisis
    └── gui_acquisition.log          # Log de interfaz gráfica
```

## 🎯 Uso Básico

### Adquisición Simple
```bash
python main_refactored.py --label "experimento1" --samples 1000 --blocks 10
```

### Adquisición con Parámetros Personalizados
```bash
python main_refactored.py \
    --label "voltaje_sensor" \
    --samples 2000 \
    --nplc 0.1 \
    --blocks 5 \
    --force
```

### Modo Estadísticas Básicas
```bash
python main_refactored.py \
    --label "test_rapido" \
    --samples 500 \
    --blocks 3 \
    --no-stats
```

### Adquisición Infinita
```bash
python main_refactored.py \
    --label "monitoreo_continuo" \
    --samples 1000 \
    --blocks 0  # 0 = modo infinito
```

### Especificar Directorio de Salida
```bash
python main_refactored.py \
    --label "experimento" \
    --samples 1000 \
    --blocks 5 \
    --output-dir "resultados_experimento"
```

### Ejemplos de Organización
```bash
# Resultados organizados por experimento
python main_refactored.py --output-dir "experimentos/sensor_voltaje"

# Resultados organizados por fecha
python main_refactored.py --output-dir "resultados/2025-10-09"

# Resultados organizados por tipo de prueba
python main_refactored.py --output-dir "calibracion/linealidad"
```

## �️ Interfaz Gráfica Avanzada

El sistema incluye una interfaz gráfica completa (`gui_interface.py`) para control intuitivo de la adquisición y análisis de datos.

### 🚀 Funcionalidades de la GUI

#### **Pestañas Principales:**
1. **Control de Adquisición**: Inicio, pausa, detención y monitoreo en tiempo real
2. **Parámetros**: Configuración completa de setpoint, Keithley y directorios
3. **Puertos**: Escaneo automático y prueba de conexiones seriales/VISA
4. **Calibración**: Control de calibración PID para Alicat
5. **Visualización**: Análisis gráfico avanzado de datos CSV
6. **Exportación**: Exportación de datos y gráficas en múltiples formatos

### 📊 Sistema de Visualización

#### **Gráficas Principales:**
- **Voltajes vs Tiempo**: Serie temporal con voltajes TIVA (crudos y filtrados) y KEITHLEY (cuando disponible)
- **Presión Alicat vs Tiempo**: Presión actual, setpoint y setpoint enviado
- **Layout**: 2 gráficas en columna (una por fila) para fácil comparación

#### **Análisis Detallado:**
- **Correlación**: Matriz de correlación entre todas las variables disponibles
- **Histogramas**: Distribuciones de variables principales (voltajes TIVA/KEITHLEY, presión, temperatura)
- **Espectro**: Análisis de frecuencia (FFT) dinámico para todas las señales disponibles
- **Tendencias**: Regresión lineal y análisis de tendencias temporales para múltiples variables

### 💾 Exportación de Datos

#### **Formatos de Datos:**
- **CSV**: Formato estándar de valores separados por comas
- **Excel (XLSX)**: Compatible con Microsoft Excel y LibreOffice
- **JSON**: Formato estructurado para aplicaciones web
- **Parquet**: Optimizado para big data y análisis masivo

#### **Formatos de Gráficas:**
- **PNG**: Alta calidad para documentos y presentaciones
- **JPG**: Comprimido para uso web
- **BMP**: Formato sin pérdida para edición
- **PDF**: Vectorial para publicaciones científicas
- **EPS**: Formato PostScript para impresión profesional

### 🎯 Cómo Usar la Interfaz Gráfica

```bash
# Activar entorno virtual
.\env\Scripts\activate

# Ejecutar interfaz gráfica
python gui_interface.py
```

#### **Flujo de Trabajo Típico:**
1. **Configurar Puertos**: Escanear y probar conexiones seriales
2. **Ajustar Parámetros**: Configurar setpoints, Keithley y directorios
3. **Iniciar Adquisición**: Comenzar captura de datos con monitoreo en tiempo real
4. **Visualizar Datos**: Cargar CSV generado y explorar gráficas
5. **Exportar Resultados**: Guardar datos y gráficas en formatos deseados

### 🔧 Características Avanzadas

- **Pausa/Reanudación**: Control preciso sobre la adquisición de datos
- **Monitoreo en Tiempo Real**: Logs detallados y estado del sistema
- **Validación Automática**: Verificación de conexiones y parámetros
- **Interfaz Intuitiva**: Diseño moderno con navegación por pestañas
- **Manejo de Errores**: Mensajes informativos y recuperación automática
- **Cierre Seguro**: Limpieza automática de recursos al cerrar la aplicación
  - Detiene threads de adquisición y calibración
  - Cierra conexiones seriales y VISA
  - Libera figuras de matplotlib
  - Cierra handlers de logging
  - Garantiza integridad de datos

## �📁 Organización de Archivos

### Estructura por Defecto
```
proyecto/
├── main_refactored.py
├── config.py
├── acquisition.py
├── analysis.py
├── plotting.py
└── output/                    # 📁 Archivos generados aquí
    ├── dc_voltage_readings_experimento1_20251009_143000.csv
    ├── voltage_analysis_experimento1_20251009_143005.png
    └── keithley_acquisition_20251009.log
```

### Personalizar Carpeta de Salida
```bash
# Usar carpeta específica
python main_refactored.py --output-dir "experimentos/voltaje"

# Usar subcarpetas por fecha
python main_refactored.py --output-dir "resultados/2025-10-09"
```

### Archivos Generados
- **CSV**: `dc_voltage_readings_[etiqueta]_[timestamp].csv`
  - Datos crudos de voltaje con metadatos
  - Columnas: Block, Sample_In_Block, Global_Sample, Voltage_V, Timestamp

- **PNG**: `voltage_analysis_[etiqueta]_[timestamp].png`
  - Gráficas completas de análisis estadístico
  - 6 paneles: serie temporal, distribución, análisis por bloques, etc.

- **LOG**: `keithley_acquisition_[fecha].log`
  - Registro completo de la ejecución
  - Información de debugging y errores

## ⚙️ Parámetros de Configuración

| Parámetro | Descripción | Valor por defecto | Rango |
|-----------|-------------|-------------------|-------|
| `--label`, `-l` | Etiqueta del experimento | `experimento` | Cualquier string |
| `--samples`, `-s` | Muestras por bloque | 2000 | 100-2000 |
| `--nplc`, `-n` | Ciclos NPLC | 10 | 0.001-100 o MINimum/MAXimum |
| `--blocks`, `-b` | Número de bloques | 50 | 0-1000 (0=infinito) |
| `--force`, `-f` | Forzar NPLC personalizados | False | - |
| `--no-stats` | Solo gráficas básicas | False | - |
| `--output-dir`, `-o` | Directorio de salida para archivos | `output` | Ruta válida |
| `--quiet`, `-q` | Modo silencioso | False | - |

### Gestión de Configuración

**Guardar configuración**:
```bash
python main_refactored.py --config-save mi_config.json --label "test" --samples 1000
```

**Cargar configuración**:
```bash
python main_refactored.py --config-load mi_config.json
```

## 📊 Análisis Estadístico

El sistema calcula automáticamente estadísticas avanzadas incluyendo:

### Estadísticas Básicas
- Media, desviación estándar, varianza
- Mínimo, máximo, rango
- Desviación media absoluta (MAD)
- Coeficiente de variación

### Estadísticas Avanzadas (con NumPy/SciPy)
- Asimetría (skewness) y curtosis
- Autocorrelación (lag 1 y completa)
- Correlación temporal
- Percentiles (Q25, Q75, IQR)
- Análisis de estabilidad

### Detección de Outliers
- Método IQR (interquartile range)
- Método Z-score
- Método Modified Z-score

## 📈 Visualización

### Gráfica Completa (por defecto)
- **Serie temporal**: Datos con líneas de referencia (media ± σ)
- **Distribución**: Histograma con KDE (si SciPy disponible)
- **Estadísticas por bloque**: Media y desviación por bloque
- **Autocorrelación**: Función de autocorrelación
- **Análisis de estabilidad**: Estadísticas móviles
- **Resumen estadístico**: Tabla completa de métricas

### Gráfica Básica (`--no-stats`)
- Serie temporal simple
- Histograma básico

## 🧪 Tests

Ejecutar todos los tests:
```bash
python -m pytest test_main.py -v
```

Ejecutar con cobertura:
```bash
python -m pytest test_main.py --cov=. --cov-report=html
```

## 🔧 Desarrollo y Mantenimiento

### Agregar Nueva Funcionalidad

1. **Para análisis estadístico**: Extender `StatisticalAnalyzer` en `analysis.py`
2. **Para visualización**: Agregar métodos a `KeithleyPlotter` en `plotting.py`
3. **Para configuración**: Modificar `KeithleyConfig` en `config.py`
4. **Para adquisición**: Extender `KeithleyAcquisition` en `acquisition.py`

### Manejo de Errores

El sistema incluye excepciones personalizadas:
- `KeithleyError`: Base para todos los errores del sistema
- `KeithleyConnectionError`: Problemas de conexión
- `KeithleyAcquisitionError`: Errores durante adquisición

### Logging

Logs se guardan automáticamente en:
- `keithley_acquisition_YYYYMMDD.log`
- Nivel INFO por defecto
- Incluye timestamps y niveles de severidad

## 🚨 Solución de Problemas

### Problema: "No se encontraron instrumentos conectados"
**Solución**:
1. Verificar conexión USB del Keithley
2. Instalar NI-VISA
3. Verificar configuración del instrumento

### Problema: "NumPy no disponible"
**Solución**:
```bash
pip install numpy
```
Algunas estadísticas estarán limitadas pero el sistema funcionará.

### Problema: "Error de timeout"
**Solución**:
- Reducir `--samples` por bloque
- Aumentar `--nplc` (menos precisión pero más rápido)
- Verificar configuración del instrumento

### Problema: Gráficas no se generan
**Solución**:
```bash
pip install matplotlib
```

## 📝 Notas de Versión

### v2.0 (Actual)
- **Modularización completa**: Código dividido en módulos independientes
- **Sistema de configuración**: Archivos JSON para configuración
- **Tests unitarios**: Cobertura completa con pytest
- **Manejo de errores mejorado**: Excepciones personalizadas
- **Documentación completa**: README y docstrings

### v1.0 (Legacy)
- Sistema monolítico en `main.py`
- Funcionalidad básica completa
- Sin tests automatizados

## 🤝 Contribución

Para contribuir:
1. Crear rama feature desde `main`
2. Agregar tests para nueva funcionalidad
3. Ejecutar todos los tests
4. Crear pull request con descripción detallada

## 📄 Licencia

Este proyecto es software libre. Consulta el archivo LICENSE para detalles.