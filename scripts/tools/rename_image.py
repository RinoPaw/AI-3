import os
from pathlib import Path
import json
# import evaluate

def rename_files():
    # 获取wav和jsons目录下的所有文件
    wav_dir = Path('assets/animations/wait/breath')
    # json_dir = Path('jsons')
    
    # 获取所有wav文件
    wav_files = list(wav_dir.glob('*.png'))
    
    # 按文件名排序，确保顺序一致
    wav_files.sort()
    
    # 从1开始编号
    counter = 1
    file_num = len(wav_files)
    error_num = 0
    
    print(f"\n开始处理，共发现 {file_num} 个文件需要重命名")
    print("=" * 50)
    
    # 重命名文件
    for wav_file in wav_files:
        try:
            # base_name = wav_file.stem  # 获取不带扩展名的文件名
            
            # 检查对应的json文件是否存在
            # json_file = json_dir / f"{base_name}.json"
            # if not json_file.exists():
            #     print(f"警告: 找不到对应的JSON文件: {json_file}")
            #     error_num += 1
            #     continue
            
            # 生成新的文件名
            new_name = f"{counter:05d}"  # 使用4位数字，如0001, 0002等
            new_wav_path = wav_dir / f"huxi_{new_name}.png"
            # new_json_path = json_dir / f"{new_name}.json"
            
            # 读取并更新json文件
            # with open(json_file, 'r', encoding='utf-8') as f:
            #     json_data = json.load(f)
            
            # 更新json中的音频路径
            # json_data['audio']['path'] = str(new_wav_path)
            
            # 保存更新后的json文件
            # with open(json_file, 'w', encoding='utf-8') as f:
            #     json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            # 重命名wav文件
            if not new_wav_path.exists():
                wav_file.rename(new_wav_path)
                print(f"✓ 重命名WAV: {wav_file.name} -> {new_wav_path.name}")
            
            # 重命名json文件
            # if not new_json_path.exists():
            #     json_file.rename(new_json_path)
            #     print(f"✓ 重命名JSON: {json_file.name} -> {new_json_path.name}")
            
            counter += 1
            
        except Exception as e:
            print(f"✗ 处理文件 {wav_file.name} 时出错: {e}")
            error_num += 1
    
    print("\n" + "=" * 50)
    print("重命名完成统计信息:")
    print(f"总文件数: {file_num}")
    print(f"成功处理: {file_num - error_num}")
    print(f"处理失败: {error_num}")
    print("=" * 50)

if __name__ == "__main__":
    rename_files() 
