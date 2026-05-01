import os


def reset_all_data():
    """Wipes all persistent data (DB and JSON state)."""
    print("🧹 Iniciando reseteo total de datos de Casino-V3...")

    import glob

    # Hardened deletion for ALL databases and WAL/SHM files
    db_patterns = ["data/*.db*", "state/*.json", "data/*.json"]
    for pattern in db_patterns:
        for fpath in glob.glob(pattern):
            try:
                os.remove(fpath)
                print(f"✅ Archivo limpiado intensivamente: {fpath}")
            except Exception as e:
                print(f"❌ Error al eliminar '{fpath}': {e}")

    print("\n✨ Sistema limpio. El próximo arranque usará balances frescos del exchange.")


if __name__ == "__main__":
    reset_all_data()
