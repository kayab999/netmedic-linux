from PIL import Image, ImageDraw

def create_netmedic_icon(path):
    size = 256
    # Crear imagen con transparencia
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 1. Fondo Circular (Sovereign Blue)
    margin = 10
    draw.ellipse([margin, margin, size-margin, size-margin], fill=(26, 35, 126, 255))
    
    # 2. Cruz Médica Blanca (Minimalista)
    cross_width = 40
    cross_length = 120
    center = size // 2
    
    # Rectángulo vertical
    draw.rectangle([center - cross_width//2, center - cross_length//2, 
                    center + cross_width//2, center + cross_length//2], fill=(255, 255, 255, 255))
    # Rectángulo horizontal
    draw.rectangle([center - cross_length//2, center - cross_width//2, 
                    center + cross_length//2, center + cross_width//2], fill=(255, 255, 255, 255))
    
    # 3. Anillos de señal de red (Health Green)
    # Dibujamos arcos para simular señal de WiFi alrededor de la cruz
    green_color = (76, 175, 80, 255)
    arc_margin = 40
    draw.arc([arc_margin, arc_margin, size-arc_margin, size-arc_margin], start=225, end=315, fill=green_color, width=12)
    draw.arc([arc_margin+30, arc_margin+30, size-arc_margin-30, size-arc_margin-30], start=225, end=315, fill=green_color, width=10)
    
    img.save(path)
    print(f"Icono guardado en: {path}")

create_netmedic_icon('/home/carlos/netmedic_linux/netmedic.png')
