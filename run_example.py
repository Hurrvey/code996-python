#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行 Code996 本地分析示例
这个脚本会生成一个示例报告
"""

import subprocess
import sys
import os

def main():
    print("=" * 60)
    print("Code996 本地版 - 示例演示")
    print("=" * 60)
    print()
    
    # 检查是否在 Git 仓库中
    try:
        subprocess.run(['git', 'status'], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        print("❌ 错误：当前目录不是 Git 仓库")
        print("请在 Git 项目目录下运行此脚本")
        sys.exit(1)
    
    print("✓ 检测到 Git 仓库")
    print()
    
    # 运行分析
    print("正在运行分析...")
    print("命令: python code996_local.py --output example_report.html")
    print()
    
    cmd = [sys.executable, 'code996_local.py', '--output', 'example_report.html']
    
    try:
        result = subprocess.run(cmd, check=True)
        print()
        print("=" * 60)
        print("✓ 分析完成！")
        print("=" * 60)
        print()
        print("📊 报告文件: example_report.html")
        print()
        print("💡 提示：")
        print("  - 双击 example_report.html 在浏览器中查看")
        print("  - 或运行: python code996_local.py --help 查看更多选项")
        print()
        
    except subprocess.CalledProcessError as e:
        print()
        print("❌ 分析失败")
        print(f"错误信息: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

