import json
import logging
import numpy as np
from flask import Flask, jsonify, send_file
from pathlib import Path
import nbtlib
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app = Flask(__name__)

BASE_DIR = Path(__file__).parent
GLOBAL_BLOCKLIST_FILE = BASE_DIR / "global_block_list.json"
OUTPUT_DIR = BASE_DIR / "output_schem"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

initialized = GLOBAL_BLOCKLIST_FILE.exists()
if not initialized:
    logging.error(f"Файл {GLOBAL_BLOCKLIST_FILE} не найден")

def generate_random_house(block_list_path, grid_size=32):
    try:
        with open(block_list_path, 'r') as f:
            block_library = json.load(f)
        block_ids = [int(id) for id in block_library.keys() if id.isdigit()]
        if not block_ids:
            raise ValueError("Пустой список блоков")
        structure = np.random.choice(block_ids, size=(grid_size, grid_size, grid_size)).astype(np.int64)
        npy_output_path = BASE_DIR / "generated_house.npy"
        np.save(npy_output_path, structure)
        unique_blocks, counts = np.unique(structure, return_counts=True)
        block_names = [block_library.get(str(id), "minecraft:air") for id in unique_blocks]
        return structure, npy_output_path, unique_blocks, block_names, counts
    except Exception as e:
        logging.error(f"Ошибка при генерации: {e}")
        raise

def create_schem_from_npy(npy_path, json_path, output_dir):
    try:
        structure = np.load(npy_path)
        if structure.ndim != 3:
            raise ValueError("Некорректный 3D массив")
        structure = np.transpose(structure, (2, 1, 0))
        with open(json_path, "r") as f:
            block_library = json.load(f)
        width, length, height = structure.shape
        schematic = nbtlib.schematic.Schematic()
        for x in range(width):
            for y in range(length):
                for z in range(height):
                    block_id = str(structure[x, y, z])
                    block_name = block_library.get(block_id, "minecraft:air")
                    schematic.blocks[x, y, z] = nbtlib.schematic.BlockState(block_name)
        output_path = output_dir / "generated_house.schem"
        schematic.save(output_path)
        return output_path
    except Exception as e:
        logging.error(f"Ошибка при создании .schem: {e}")
        raise

@app.route("/health", methods=["GET"])
def health():
    if not initialized:
        return jsonify({"status": "unavailable", "message": "Отсутствует global_block_list.json"}), 404
    return jsonify({"status": "available", "message": "Сервис готов к работе"}), 200

@app.route("/generate", methods=["POST"])
def generate():
    if not initialized:
        return jsonify({"status": "error", "message": "Отсутствует global_block_list.json"}), 500
    try:
        pred_ids, npy_output_path, unique_blocks, block_names, counts = generate_random_house(str(GLOBAL_BLOCKLIST_FILE))
        schem_file = create_schem_from_npy(npy_output_path, str(GLOBAL_BLOCKLIST_FILE), OUTPUT_DIR)
        block_counts = [{"id": int(id), "name": name, "count": int(count)} for id, name, count in zip(unique_blocks, block_names, counts)]
        return send_file(
            str(schem_file),
            mimetype="application/octet-stream",
            download_name="generated_house.schem",
            as_attachment=True
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)