import os

tiles_dir = "public/tiles"
for z_str in os.listdir(tiles_dir):
    z_path = os.path.join(tiles_dir, z_str)
    if not os.path.isdir(z_path): continue
    
    try:
        z = int(z_str)
    except ValueError:
        continue
        
    y_max = (2 ** z) - 1
    
    for x_str in os.listdir(z_path):
        x_path = os.path.join(z_path, x_str)
        if not os.path.isdir(x_path): continue
        
        # We need to collect the files to rename first to avoid conflicts
        renames = {}
        for file in os.listdir(x_path):
            if file.endswith(".png"):
                y_old_str = file.split(".")[0]
                try:
                    y_old = int(y_old_str)
                    y_new = y_max - y_old
                    renames[y_old] = y_new
                except ValueError:
                    pass
                    
        # Rename using a temporary suffix to avoid collisions
        for y_old, y_new in renames.items():
            old_file = os.path.join(x_path, f"{y_old}.png")
            tmp_file = os.path.join(x_path, f"{y_new}_tmp.png")
            os.rename(old_file, tmp_file)
            
        for y_new in renames.values():
            tmp_file = os.path.join(x_path, f"{y_new}_tmp.png")
            new_file = os.path.join(x_path, f"{y_new}.png")
            os.rename(tmp_file, new_file)

print("Tiles fixed to XYZ format!")
