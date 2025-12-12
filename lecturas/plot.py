import pandas as pd
import matplotlib.pyplot as plt
from tkinter import Tk
from tkinter.filedialog import askopenfilename
import os

# ---------------------- Seleccionar archivo CSV ----------------------
Tk().withdraw()  # Ocultamos la ventana principal de Tkinter
print("Selecciona tu archivo CSV...")
archivo = askopenfilename(
    title="Selecciona el archivo CSV con los datos",
    filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")]
)

if not archivo:
    print("No se seleccionó ningún archivo. Saliendo...")
    exit()

# ---------------------- Leer el archivo ----------------------
# Leemos el CSV
df = pd.read_csv(archivo)

# Normalizamos nombres de columnas (MATLAB y Python convierten espacios y paréntesis de forma distinta)
df.columns = (df.columns
              .str.strip()
              .str.replace(' ', '_')
              .str.replace('(', '')
              .str.replace(')', '')
              .str.replace('/', '_'))

# Verificamos que existan las columnas esperadas
columnas_requeridas = [
    'TIVA_Voltage_V',
    'TIVA_Voltage_w_FPBV',
    'KEITHLEY_Voltage_V',
    'Alicat_Presion_kPA',
    'Alicat_Setpoint_kPA',
    'Setpoint_Enviado_kPA',
    'Sample'
]

faltantes = [col for col in columnas_requeridas if col not in df.columns]
if faltantes:
    print("Columnas no encontradas:", faltantes)
    print("Columnas disponibles:", list(df.columns))
    exit()

# ---------------------- Graficar con dos ejes Y ----------------------
fig, ax1 = plt.subplots(figsize=(12, 6))

# Eje izquierdo: Voltajes
color_tiva = '#1f77b4'      # azul
color_tiva_fpb = '#ff7f0e'  # naranja
color_keith = '#d62728'     # rojo

ax1.plot(df['Sample'], df['TIVA_Voltage_V'],         label='TIVA Voltage',           color=color_tiva,    linewidth=2)
ax1.plot(df['Sample'], df['TIVA_Voltage_w_FPBV'],   label='TIVA Voltage w/FPB',      color=color_tiva_fpb, linewidth=2, linestyle='--')
ax1.plot(df['Sample'], df['KEITHLEY_Voltage_V'],     label='KEITHLEY Voltage',        color=color_keith,   linewidth=2)
ax1.set_xlabel('Muestra (#)', fontsize=12)
ax1.set_ylabel('Voltaje (V)', color='black', fontsize=12)
ax1.tick_params(axis='y', labelcolor='black')
ax1.grid(True, alpha=0.3)

# Eje derecho: Presiones
ax2 = ax1.twinx()
color_presion = '#2ca02c'      # verde
color_setpoint_a = '#9467bd'   # púrpura
color_setpoint_e = '#8c564b'   # marrón

ax2.plot(df['Sample'], df['Alicat_Presion_kPA'],        label='Alicat Presión',       color=color_presion,  linewidth=2.5)
ax2.plot(df['Sample'], df['Alicat_Setpoint_kPA'],     label='Alicat Setpoint',      color=color_setpoint_a, linewidth=2, linestyle='--')
ax2.plot(df['Sample'], df['Setpoint_Enviado_kPA'],     label='Setpoint Enviado',     color=color_setpoint_e, linewidth=2, linestyle=':')
ax2.set_ylabel('Presión (kPa)', color='black', fontsize=12)

# Leyenda combinada (ambos ejes)
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', bbox_to_anchor=(1.02, 1), borderaxespad=0)

# Título
nombre_archivo = os.path.basename(archivo)
plt.title(f'Mediciones TIVA + Control de Presión Alicat\n{nombre_archivo}', fontsize=14, pad=20)

# Ajustes finales
plt.tight_layout()
plt.show()

print("¡Gráfico generado con éxito!")