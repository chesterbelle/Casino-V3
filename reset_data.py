import os
import sqlite3


def reset_all_data():
    """Wipes all persistent data (DB and JSON state)."""
    print("🧹 Iniciando reseteo total de datos de Casino-V3...")

    # 1. Resetear Base de Datos SQLite
    db_path = "data/casino_v3.db"
    if os.path.exists(db_path):
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute("DROP TABLE IF EXISTS trades")
                print(f"✅ Tabla 'trades' eliminada de '{db_path}'.")
                conn.commit()
            # The Historian will recreate it on init
        except Exception as e:
            print(f"❌ Error al limpiar DB: {e}")
    else:
        print(f"ℹ️ El archivo DB '{db_path}' no existe todavía.")

    # 2. Resetear Estado del Bot y Archivos de Sesión
    import glob

    # Eliminar todos los archivos session_*.json y bot_state.json en data/ y state/
    files_to_delete = glob.glob("data/session_*.json")
    files_to_delete.extend(glob.glob("state/session_*.json"))

    if os.path.exists("data/bot_state.json"):
        files_to_delete.append("data/bot_state.json")
    if os.path.exists("state/bot_state.json"):
        files_to_delete.append("state/bot_state.json")

    for fpath in files_to_delete:
        try:
            os.remove(fpath)
            print(f"✅ Archivo de estado eliminado: {fpath}")
        except Exception as e:
            print(f"❌ Error al eliminar {fpath}: {e}")

    print("\n✨ Sistema limpio. El próximo arranque usará balances frescos del exchange.")


if __name__ == "__main__":
    reset_all_data()
