"""RapidOCR 命令行入口：python run_rapidocr.py <image_path> [--lines]
输出每行：置信度 + 文本。--lines 只输出纯文本。"""
import sys

def main():
    img = None
    lines_only = False
    for a in sys.argv[1:]:
        if a == "--lines":
            lines_only = True
        else:
            img = a
    if not img:
        print("usage: run_rapidocr.py <image_path> [--lines]", file=sys.stderr)
        sys.exit(2)

    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()
    result, elapse = ocr(img)
    if not result:
        print("(no text recognized)")
        return
    for box, text, score in result:
        if lines_only:
            print(text)
        else:
            print(f"{float(score):.2f}  {text}")

if __name__ == "__main__":
    main()
