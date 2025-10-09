"""
Configuración y validaciones para el sistema de adquisición Keithley
"""
import argparse
from typing import Dict, Any, Tuple, Optional
import os


class KeithleyConfig:
    """Clase para manejar la configuración del sistema Keithley"""

    # Valores válidos para NPLCycles
    VALID_NPLC_VALUES = [0.001, 0.006, 0.02, 0.06, 0.2, 0.6, 1, 2, 10, 100, "MINimum", "MAXimum"]

    def __init__(self):
        self.args = None
        self._setup_parser()

    def _setup_parser(self) -> None:
        """Configura el parser de argumentos de línea de comandos"""
        self.parser = argparse.ArgumentParser(
            description='Sistema de adquisición de datos Keithley con análisis estadístico',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog='''
Ejemplos de uso:
  # Adquisición básica con gráficas completas
  python main.py --label "experimento1" --samples 1000 --nplc 1 --blocks 10

  # Adquisición con gráficas básicas únicamente
  python main.py --label "experimento2" --samples 500 --nplc 0.1 --blocks 5 --no-stats

  # Adquisición con NPLC personalizado (requiere --force)
  python main.py --label "experimento3" --samples 2000 --nplc 5 --force --blocks 0

  # Modo configuración (guarda configuración en archivo)
  python main.py --config-save config.json --label "test" --samples 100
    '''
        )

        # Argumentos principales
        self.parser.add_argument('--label', '-l', type=str, default='experimento',
                               help='Etiqueta del experimento (default: experimento)')
        self.parser.add_argument('--samples', '-s', type=int, default=2000,
                               help='Muestras por conteo (100-2000, default: 2000)')
        self.parser.add_argument('--nplc', '-n', type=str, default='10',
                               help='Ciclos NPLC (0.001-100 o MINimum/MAXimum, default: 10)')
        self.parser.add_argument('--blocks', '-b', type=int, default=50,
                               help='Número de bloques (0=indefinido, 1-1000, default: 50)')
        self.parser.add_argument('--force', '-f', action='store_true',
                               help='Forzar valores NPLC personalizados')
        self.parser.add_argument('--no-stats', '-ns', action='store_true',
                               help='Solo generar gráficas básicas (sin estadísticas avanzadas)')

        # Argumentos de configuración
        self.parser.add_argument('--config-save', type=str,
                               help='Guardar configuración actual en archivo JSON')
        self.parser.add_argument('--config-load', type=str,
                               help='Cargar configuración desde archivo JSON')

        # Argumentos de salida
        self.parser.add_argument('--output-dir', '-o', type=str, default='.',
                               help='Directorio de salida para archivos (default: .)')
        self.parser.add_argument('--quiet', '-q', action='store_true',
                               help='Modo silencioso (menos output en consola)')

    def parse_args(self) -> argparse.Namespace:
        """Parsea los argumentos de línea de comandos"""
        self.args = self.parser.parse_args()
        return self.args

    def validate_config(self) -> Tuple[bool, Optional[str]]:
        """
        Valida la configuración actual

        Returns:
            Tuple[bool, Optional[str]]: (válido, mensaje de error)
        """
        if not self.args:
            return False, "No se han parseado los argumentos"

        # Validar muestras por conteo
        if self.args.samples < 100 or self.args.samples > 2000:
            return False, f"Muestras por conteo debe estar entre 100-2000. Valor actual: {self.args.samples}"

        # Validar NPLCycles
        try:
            if self.args.nplc in ["MINimum", "MAXimum"]:
                if not self.args.force and self.args.nplc not in self.VALID_NPLC_VALUES:
                    return False, f"NPLCycles debe ser uno de {self.VALID_NPLC_VALUES}. Use --force para valores personalizados."
            else:
                nplc_float = float(self.args.nplc)
                if not self.args.force and nplc_float not in self.VALID_NPLC_VALUES:
                    return False, f"NPLCycles debe ser uno de {self.VALID_NPLC_VALUES}. Use --force para valores personalizados."
        except ValueError:
            return False, f"Valor inválido para NPLCycles: {self.args.nplc}"

        # Validar número de bloques
        if self.args.blocks < 0 or self.args.blocks > 1000:
            return False, f"Número de bloques debe estar entre 0-1000. Valor actual: {self.args.blocks}"

        # Validar directorio de salida
        if not os.path.exists(self.args.output_dir):
            try:
                os.makedirs(self.args.output_dir)
            except Exception as e:
                return False, f"No se puede crear directorio de salida: {e}"

        return True, None

    def get_processed_config(self) -> Dict[str, Any]:
        """
        Retorna la configuración procesada y validada

        Returns:
            Dict con la configuración procesada
        """
        if not self.args:
            raise ValueError("Debe parsear argumentos primero")

        # Procesar NPLCycles
        try:
            if self.args.nplc in ["MINimum", "MAXimum"]:
                nplc_cycles = self.args.nplc
            else:
                nplc_cycles = float(self.args.nplc)
        except ValueError:
            nplc_cycles = 10  # fallback

        return {
            'experiment_label': self.args.label,
            'samples_per_count': self.args.samples,
            'nplc_cycles': nplc_cycles,
            'num_blocks': self.args.blocks,
            'force_nplc': self.args.force,
            'no_stats': self.args.no_stats,
            'output_dir': self.args.output_dir,
            'quiet': self.args.quiet,
            'infinite_mode': (self.args.blocks == 0)
        }

    def save_config(self, filepath: str) -> None:
        """Guarda la configuración actual en un archivo JSON"""
        import json

        config = self.get_processed_config()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"✅ Configuración guardada en: {filepath}")

    def load_config(self, filepath: str) -> None:
        """Carga configuración desde un archivo JSON"""
        import json

        with open(filepath, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # Actualizar argumentos con valores cargados
        for key, value in config.items():
            if hasattr(self.args, key):
                setattr(self.args, key, value)


# Instancia global para uso fácil
config = KeithleyConfig()