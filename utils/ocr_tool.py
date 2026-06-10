"""
PaddleOCR 本地识别工具 — 支持中英文混合识别。

首次运行时 PaddleOCR 会自动下载模型文件到 ~/.paddleocr/。
"""
from typing import List, Optional
from PIL import Image


class OCREngine:
    """PaddleOCR 封装，懒加载单例。"""

    _instance: Optional["OCREngine"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def _init(self):
        if self._initialized:
            return
        print("[OCR] 正在加载 PaddleOCR 模型（首次较慢）...")
        from paddleocr import PaddleOCR

        # 自动检测 GPU，没有则降级 CPU
        try:
            import paddle
            gpu_available = paddle.is_compiled_with_cuda()
        except Exception:
            gpu_available = False

        use_gpu = gpu_available
        if use_gpu:
            print("[OCR] 检测到 GPU，使用 GPU 加速")
        else:
            print("[OCR] 未检测到 GPU，使用 CPU（较慢但可用）")

        self._ocr = PaddleOCR(
            use_angle_cls=True,
            lang='ch',
            use_gpu=use_gpu,
            show_log=False,
        )
        self._initialized = True
        print("[OCR] PaddleOCR 模型加载完成")

    def recognize(self, pil_image: Image.Image) -> str:
        """识别单张 PIL 图片，返回文本字符串。"""
        self._init()
        import numpy as np

        # PaddleOCR 需要 numpy array (RGB)
        img_array = np.array(pil_image.convert("RGB"))

        try:
            results = self._ocr.ocr(img_array, cls=True)
        except Exception as e:
            return f"[OCR 识别失败] {e}"

        if not results or not results[0]:
            return "[OCR] 未识别到文字"

        lines = []
        for line_info in results[0]:
            text = line_info[1][0]  # (bbox, (text, confidence))
            confidence = line_info[1][1]
            lines.append(f"{text}  ({confidence:.0%})")

        return "\n".join(lines)

    def recognize_batch(self, images: List[Image.Image]) -> str:
        """批量识别多张图片，返回汇总文本。"""
        if not images:
            return ""

        results = []
        for i, img in enumerate(images, 1):
            text = self.recognize(img)
            if len(images) > 1:
                results.append(f"## 截图 {i}\n{text}")
            else:
                results.append(text)

        return "\n\n".join(results)


def ocr_recognize(pil_image: Image.Image) -> str:
    """便捷函数：识别单张图片。"""
    return OCREngine().recognize(pil_image)


def ocr_recognize_batch(images: List[Image.Image]) -> str:
    """便捷函数：批量识别多张图片。"""
    return OCREngine().recognize_batch(images)
