#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown文档转换工具
支持转换为：PDF、Word、HTML
"""

import os
import sys

def convert_to_pdf(md_file, output_file=None):
    """转换为PDF"""
    try:
        import pypandoc
        if output_file is None:
            output_file = md_file.replace('.md', '.pdf')
        
        print(f"正在转换为PDF: {output_file}...")
        pypandoc.convert_file(
            md_file,
            'pdf',
            outputfile=output_file,
            extra_args=['--pdf-engine=xelatex', '-V', 'mainfont=PingFang SC', '-V', 'geometry:margin=2cm', '--toc']
        )
        print(f"✅ PDF已生成: {output_file}")
        return True
    except ImportError:
        print("❌ 需要安装 pypandoc: pip install pypandoc")
        return False
    except Exception as e:
        print(f"❌ PDF转换失败: {e}")
        print("提示: 需要安装 LaTeX (macOS: brew install --cask basictex)")
        return False

def convert_to_docx(md_file, output_file=None):
    """转换为Word"""
    try:
        import pypandoc
        if output_file is None:
            output_file = md_file.replace('.md', '.docx')
        
        print(f"正在转换为Word: {output_file}...")
        pypandoc.convert_file(md_file, 'docx', outputfile=output_file, extra_args=['--toc'])
        print(f"✅ Word已生成: {output_file}")
        return True
    except ImportError:
        print("❌ 需要安装 pypandoc: pip install pypandoc")
        return False
    except Exception as e:
        print(f"❌ Word转换失败: {e}")
        return False

def convert_to_html(md_file, output_file=None):
    """转换为HTML"""
    try:
        import markdown
        if output_file is None:
            output_file = md_file.replace('.md', '.html')
        
        print(f"正在转换为HTML: {output_file}...")
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        html = markdown.markdown(md_content, extensions=['toc', 'tables', 'fenced_code', 'codehilite'])
        
        html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>加密货币多因子数据分析报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 4px solid #3498db;
            padding-bottom: 15px;
            margin-bottom: 30px;
            font-size: 2.5em;
        }}
        h2 {{
            color: #34495e;
            margin-top: 40px;
            margin-bottom: 20px;
            padding-left: 10px;
            border-left: 4px solid #3498db;
            font-size: 1.8em;
        }}
        h3 {{
            color: #555;
            margin-top: 30px;
            margin-bottom: 15px;
            font-size: 1.4em;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
            font-size: 14px;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: #3498db;
            color: white;
            font-weight: bold;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        tr:hover {{
            background-color: #f1f1f1;
        }}
        code {{
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: "Courier New", monospace;
            color: #e83e8c;
        }}
        pre {{
            background-color: #282c34;
            color: #abb2bf;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            margin: 20px 0;
        }}
        pre code {{
            background-color: transparent;
            color: inherit;
            padding: 0;
        }}
        blockquote {{
            border-left: 4px solid #3498db;
            padding-left: 20px;
            margin: 20px 0;
            color: #666;
            font-style: italic;
        }}
        ul, ol {{
            margin: 15px 0;
            padding-left: 30px;
        }}
        li {{
            margin: 8px 0;
        }}
        a {{
            color: #3498db;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .toc {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        @media print {{
            body {{
                background-color: white;
            }}
            .container {{
                box-shadow: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        {html}
    </div>
</body>
</html>"""
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_template)
        
        print(f"✅ HTML已生成: {output_file}")
        return True
    except ImportError:
        print("❌ 需要安装 markdown: pip install markdown")
        return False
    except Exception as e:
        print(f"❌ HTML转换失败: {e}")
        return False

def main():
    md_file = '加密货币多因子数据分析报告.md'
    
    if not os.path.exists(md_file):
        print(f"❌ 文件不存在: {md_file}")
        print(f"当前目录: {os.getcwd()}")
        sys.exit(1)
    
    print("=" * 60)
    print("Markdown文档转换工具")
    print("=" * 60)
    print(f"源文件: {md_file}")
    print()
    print("选择转换格式:")
    print("1. PDF (需要 pandoc 和 LaTeX)")
    print("2. Word (DOCX) (需要 pandoc)")
    print("3. HTML (需要 markdown 库)")
    print("4. 全部")
    print()
    
    choice = input("请输入选项 (1-4): ").strip()
    
    print()
    
    if choice == '1':
        convert_to_pdf(md_file)
    elif choice == '2':
        convert_to_docx(md_file)
    elif choice == '3':
        convert_to_html(md_file)
    elif choice == '4':
        convert_to_html(md_file)  # HTML最简单，先转换
        convert_to_docx(md_file)
        convert_to_pdf(md_file)
    else:
        print("❌ 无效选项")
        sys.exit(1)
    
    print()
    print("=" * 60)
    print("转换完成！")
    print("=" * 60)

if __name__ == '__main__':
    main()

