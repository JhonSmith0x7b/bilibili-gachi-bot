import httpx
import io
import base64
import logging
from PIL import Image

async def process_image_for_bot(url: str, max_kb: int = 500) -> str:
    """
    Download image from URL, compress if it exceeds max_kb, and return as base64 string.
    """
    try:
        # 1. Download image
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/"
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            img_bytes = response.content
            
        initial_size = len(img_bytes)
        if initial_size <= max_kb * 1024:
            return f"base64://{base64.b64encode(img_bytes).decode('utf-8')}"

        # 2. Compress using Pillow
        logging.info(f"Image size {initial_size/1024:.1f}KB exceeds {max_kb}KB, compressing...")
        
        # Load image into Pillow
        img = Image.open(io.BytesIO(img_bytes))
        
        # Convert to RGB if necessary (JPEG doesn't support RGBA)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        quality = 85
        output = io.BytesIO()
        
        # Iteratively reduce quality until size is within limit
        while quality > 10:
            output.seek(0)
            output.truncate()
            img.save(output, format="JPEG", quality=quality)
            current_bytes = output.getvalue()
            if len(current_bytes) <= max_kb * 1024:
                break
            quality -= 10
            
        final_bytes = output.getvalue()
        logging.info(f"Compressed image from {initial_size/1024:.1f}KB to {len(final_bytes)/1024:.1f}KB (quality={quality})")
        
        return f"base64://{base64.b64encode(final_bytes).decode('utf-8')}"
        
    except Exception as e:
        logging.error(f"Error processing image from {url}: {e}")
        # Fallback to original URL if anything goes wrong
        return url
