
import json
import logging
import numpy as np
from flask import Flask, jsonify, send_file
from pathlib import Path
import nbtlib
from nbtlib.tag import Compound, ByteArray, Int, String, List

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
            logging.error("В global_block_list.json не найдено ни одного числового ID блока")
            raise ValueError("Пустой список блоков")

        structure = np.random.choice(block_ids, size=(grid_size, grid_size, grid_size)).astype(np.int64)
        logging.info(f"Сгенерирован массив формы: {structure.shape}")

        npy_output_path = BASE_DIR / "generated_house.npy"
        np.save(npy_output_path, structure)
        logging.info(f"Сгенерированный дом сохранён в {npy_output_path}")

        unique_blocks, counts = np.unique(structure, return_counts=True)
        block_names = []
        for id in unique_blocks:
            block_info = block_library.get(str(id), "minecraft:air")
            block_name = block_info.get('name', block_info) if isinstance(block_info, dict) else block_info
            block_names.append(block_name)

        return structure, npy_output_path, unique_blocks, block_names, counts

    except Exception as e:
        logging.error(f"Ошибка при генерации случайного дома: {e}")
        raise

def create_schem_from_npy(npy_path, json_path, output_dir):
    try:
        structure = np.load(npy_path)
        if structure.ndim != 3:
            logging.error(f"Файл {npy_path} не является 3D массивом.")
            return False

        structure = np.transpose(structure, (2, 1, 0))
        logging.info(f"Порядок осей после транспонирования: (2, 1, 0) -> (x, z, y)")

        unique_values = np.unique(structure).astype(str)
        logging.info(f"Уникальные значения в .npy: {unique_values}")
        logging.info(f"Размер структуры: {structure.shape}, первый срез: {structure[0, 0, :]}")

        with open(json_path, "r") as f:
            block_library = json.load(f)
           
        for val in unique_values:
            if val not in block_library and val != "0":
                logging.warning(f"Значение {val} из .npy отсутствует в .json, будет заменено на minecraft:air")

        width, length, height = structure.shape
        logging.info(f"Размеры структуры: Width={width}, Height={height}, Length={length}")

        schematic = Compound({
            "Version": Int(2),
            "DataVersion": Int(2730),
            "Width": Int(width),
            "Height": Int(height),
            "Length": Int(length),
            "PaletteMax": Int(0),
            "Palette": Compound(),
            "BlockData": ByteArray(),
            "BlockEntities": List(),
            "Entities": List()
        })

        palette = {}
        palette_index = 0

        palette["minecraft:air"] = Int(0)
        palette_index += 1

        for block_id in unique_values:
            if block_id == "0":
                continue
            block_name = block_library.get(block_id, "minecraft:air")
            if block_name not in palette:
                palette[block_name] = Int(palette_index)
                logging.info(f"Добавлен блок в палитру: {block_name} -> индекс {palette_index}")
                palette_index += 1

        schematic["Palette"] = Compound(palette)
        schematic["PaletteMax"] = Int(palette_index)

        total_blocks = width * height * length
        block_data_bytes = bytearray(total_blocks)

        index = 0
        for y in range(height):
            for z in range(length):
                for x in range(width):
                    block_id = str(structure[x, z, y])
                    block_name = block_library.get(block_id, "minecraft:air")
                    block_index = palette.get(block_name, 0)
                    block_data_bytes[index] = block_index
                    index += 1

        schematic["BlockData"] = ByteArray(block_data_bytes)
        logging.info(f"BlockData заполнен: {len(block_data_bytes)} байт")

        output_path = output_dir / f"{Path(npy_path).stem}.schem"
        nbtlib.File(schematic).save(output_path, gzipped=True)
        logging.info(f"Создан файл {output_path}")
        return True

    except Exception as e:
        logging.error(f"Ошибка при обработке {npy_path}: {str(e)}")
        return False

@app.route("/generate", methods=["POST"])
def generate():
    if not initialized:
        return jsonify({"status": "error", "message": "Сервис не инициализирован: отсутствует global_block_list.json"}), 500

    try:
        logging.info("Генерация дома")
        pred_ids, npy_output_path, unique_blocks, block_names, counts = generate_random_house(
            block_list_path=str(GLOBAL_BLOCKLIST_FILE)
        )

        success = create_schem_from_npy(npy_output_path, str(GLOBAL_BLOCKLIST_FILE), OUTPUT_DIR)
        if not success:
            return jsonify({"status": "error", "message": "Ошибка при создании .schem файла"}), 500

        schem_file = OUTPUT_DIR / f"{Path(npy_output_path).stem}.schem"

        result = {
            "status": "success",
            "npy_file": str(npy_output_path),
            "schem_file": str(schem_file),
            "blocks": [
                {"id": int(id), "name": name, "count": int(count)}
                for id, name, count in zip(unique_blocks, block_names, counts)
            ],
            "description": "House generated and converted to .schem successfully"
        }
        logging.info(f"Генерация завершена: {schem_file}")

        return send_file(
            str(schem_file),
            mimetype="application/octet-stream",
            download_name="generated_house.schem",
            as_attachment=True
        )

    except Exception as e:
        logging.error(f"Ошибка при генерации: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    if not initialized:
        return jsonify({"status": "unavailable", "message": "Сервис не инициализирован: отсутствует global_block_list.json"}), 404
    return jsonify({"status": "available", "message": "Сервис готов к работе"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
   