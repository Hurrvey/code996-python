#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Code996 本地版本
统计 Git 项目的 commit 时间分布，并生成本地HTML页面展示结果
"""

import subprocess
import sys
import os
import json
from datetime import datetime
from collections import defaultdict
import argparse
import math
import webbrowser
import tempfile
import shutil
import re


def parse_repo_list(args):
    """
    解析命令行参数，返回统一格式的仓库列表
    
    Args:
        args: argparse解析后的参数对象
    
    Returns:
        list: [{'path': 'xxx', 'type': 'local'/'remote'}, ...]
    """
    repos = []
    
    # 处理 --repos（逗号分隔）
    if args.repos:
        for path in args.repos.split(','):
            path = path.strip()
            if path:
                repos.append({'path': path, 'type': 'local'})
    
    # 处理 --urls（逗号分隔）
    if args.urls:
        for url in args.urls.split(','):
            url = url.strip()
            if url:
                repos.append({'path': url, 'type': 'remote'})
    
    # 处理 --repo 多次传入（action='append'）
    if args.repo and isinstance(args.repo, list):
        for path in args.repo:
            if path:
                repos.append({'path': path, 'type': 'local'})
    
    # 处理 --url 多次传入（action='append'）
    if args.url and isinstance(args.url, list):
        for url in args.url:
            if url:
                repos.append({'path': url, 'type': 'remote'})
    
    # 处理 --input-file
    if args.input_file:
        if not os.path.exists(args.input_file):
            print(f"错误: 文件不存在: {args.input_file}", file=sys.stderr)
            sys.exit(1)
        
        with open(args.input_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # 跳过空行和纯注释行
                if not line or line.startswith('#'):
                    continue
                
                # 移除行内注释
                if '#' in line:
                    line = line.split('#')[0].strip()
                
                if not line:
                    continue
                
                # 判断是本地路径还是 URL
                if line.startswith('http://') or line.startswith('https://') or line.startswith('git@'):
                    repos.append({'path': line, 'type': 'remote'})
                else:
                    repos.append({'path': line, 'type': 'local'})
    
    # 如果没有提供任何仓库参数，默认当前目录（单仓库模式）
    if not repos:
        repos.append({'path': '.', 'type': 'local'})
    
    return repos


def validate_repo_params(args):
    """
    验证仓库参数的有效性，防止新旧参数混用
    
    Args:
        args: argparse解析后的参数对象
    
    Raises:
        SystemExit: 参数配置错误时退出
    """
    # 检测是否使用了多仓库参数
    multi_repo_params = bool(args.repos or args.urls or args.input_file)
    
    # 检测是否使用了传统单仓库参数（但不是默认值）
    # 注意：--repo 和 --url 现在支持多次传入，所以允许它们出现
    # 只要不是与 --repos/--urls/--input-file 同时出现就行
    
    # 如果同时使用了逗号分隔参数和多次传入参数，给出警告但允许（它们会合并）
    if multi_repo_params and (args.repo or args.url):
        print("⚠️  提示: 同时使用了多种仓库参数格式，将合并所有仓库进行分析", file=sys.stderr)
    
    return True


class Code996Analyzer:
    def __init__(self, start_date=None, end_date=None, author=None, repo_path=".", remote_url=None):
        self.start_date = start_date or "2022-01-01"
        self.end_date = end_date or datetime.now().strftime("%Y-%m-%d")
        self.author = author or ""
        self.repo_path = repo_path
        self.remote_url = remote_url
        self.temp_dir = None  # 用于存储临时克隆的目录
        self.project_name = None  # 项目名称
        
    def get_project_name(self):
        """获取项目名称"""
        if self.project_name:
            return self.project_name
        
        try:
            # 尝试从 git remote 获取
            cmd = ["git", "-C", self.repo_path, "remote", "get-url", "origin"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode == 0 and result.stdout.strip():
                # 从 URL 中提取项目名
                # 例如：https://github.com/user/repo.git -> user/repo
                url = result.stdout.strip()
                # 移除 .git 后缀
                url = re.sub(r'\.git$', '', url)
                # 提取用户名/项目名部分
                match = re.search(r'[:/]([^/]+/[^/]+)/?$', url)
                if match:
                    self.project_name = match.group(1).replace('/', '-')
                    return self.project_name
            
            # 如果从 remote 获取失败，使用目录名
            self.project_name = os.path.basename(os.path.abspath(self.repo_path))
            
        except Exception:
            # 出错时使用目录名
            self.project_name = os.path.basename(os.path.abspath(self.repo_path))
        
        return self.project_name
    
    def clone_remote_repo(self):
        """克隆远程仓库（仅克隆 .git 目录）"""
        if not self.remote_url:
            return
        
        print(f"正在克隆远程仓库: {self.remote_url}")
        print("正在下载 Git 历史数据（不下载工作文件）...")
        
        # 从 URL 中提取项目名
        url = re.sub(r'\.git$', '', self.remote_url)
        match = re.search(r'[:/]([^/]+/[^/]+)/?$', url)
        if match:
            self.project_name = match.group(1).replace('/', '-')
        else:
            self.project_name = "unknown-project"
        
        # 创建 online_project 目录
        online_dir = "online_project"
        if not os.path.exists(online_dir):
            os.makedirs(online_dir)
        
        # 为每个项目创建独立目录
        self.temp_dir = os.path.join(online_dir, self.project_name)
        
        # 如果目录已存在，添加时间戳避免冲突
        if os.path.exists(self.temp_dir):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.temp_dir = os.path.join(online_dir, f"{self.project_name}_{timestamp}")
        
        try:
            # 使用 --bare 克隆，只下载 Git 对象，不下载工作文件
            # 这样可以大幅减少下载量和时间
            cmd = ["git", "clone", "--bare", "--depth", "1000", self.remote_url, self.temp_dir]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # 更新 repo_path 为 bare 仓库路径
            self.repo_path = self.temp_dir
            print(f"✓ 仓库克隆完成（仅 Git 历史数据）")
            print(f"📁 保存位置: {self.temp_dir}")
            
        except subprocess.CalledProcessError as e:
            print(f"克隆失败: {e.stderr}", file=sys.stderr)
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            sys.exit(1)
    
    def cleanup(self):
        """清理临时目录（可选）"""
        # 注意：对于远程仓库，我们保留在 online_project 目录中以便复用
        # 如果需要清理，可以手动删除 online_project 目录
        # 这里不自动清理，让用户可以复用已下载的仓库
        if self.temp_dir and self.remote_url:
            # 远程仓库保留不删除
            print(f"\n💡 提示: 远程仓库已保存在 {self.temp_dir}")
            print(f"   如需再次分析同一项目，可直接使用: --repo {self.temp_dir}")
            print(f"   如需清理，请手动删除 online_project 目录")
        elif self.temp_dir and os.path.exists(self.temp_dir) and not self.remote_url:
            # 只清理非远程的临时目录
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                print(f"警告: 清理临时文件失败: {e}", file=sys.stderr)
    
    def run_git_command(self, date_format):
        """运行git log命令获取统计数据"""
        cmd = [
            "git", "-C", self.repo_path, "log",
            f"--author={self.author}",
            f"--date=format:{date_format}",
            f"--after={self.start_date}",
            f"--before={self.end_date}"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"Git命令执行失败: {e}", file=sys.stderr)
            self.cleanup()
            sys.exit(1)
    
    def parse_date_output(self, output):
        """解析git log输出，统计每个时间点的commit数"""
        counts = defaultdict(int)
        for line in output.split('\n'):
            if line.startswith('Date:'):
                # 提取日期部分
                date_value = line.split()[1].strip()
                counts[date_value] += 1
        return counts
    
    def get_hour_stats(self):
        """获取按小时统计的commit数据"""
        output = self.run_git_command("%H")
        hour_counts = self.parse_date_output(output)
        
        # 转换为列表格式，确保所有小时都有数据
        hour_data = []
        for hour in sorted(hour_counts.keys()):
            hour_data.append({
                "time": hour,
                "count": hour_counts[hour]
            })
        
        return hour_data
    
    def get_week_stats(self):
        """获取按星期统计的commit数据"""
        output = self.run_git_command("%u")
        week_counts = self.parse_date_output(output)
        
        # 星期标签（1=Monday, 7=Sunday）
        week_labels = {
            '1': '周一', '2': '周二', '3': '周三', '4': '周四',
            '5': '周五', '6': '周六', '7': '周日'
        }
        
        # 确保所有天都有数据
        week_data = []
        for day in ['1', '2', '3', '4', '5', '6', '7']:
            week_data.append({
                "time": week_labels[day],
                "count": week_counts.get(day, 0)
            })
        
        return week_data
    
    def calculate_work_time_range(self, hour_data):
        """计算工作时间范围（上班时间和下班时间）"""
        if not hour_data:
            return None, None
        
        # 计算平方平均数
        total_count = sum(item['count'] for item in hour_data)
        if total_count == 0:
            return None, None
        
        quadratic_value = sum(item['count'] ** 2 for item in hour_data) / len(hour_data)
        standard_value = math.sqrt(quadratic_value)
        
        # 筛选工作时间（score >= 0.45）
        work_hours = [item for item in hour_data if item['count'] / standard_value >= 0.45]
        
        # 开工时间段（8-12点）
        opening_data = [item for item in work_hours if 8 <= int(item['time']) <= 12]
        # 收工时间段（17-23点）
        closing_data = [item for item in work_hours if 17 <= int(item['time']) <= 23]
        
        opening_time = min(opening_data, key=lambda x: int(x['time'])) if opening_data else None
        closing_time = max(closing_data, key=lambda x: int(x['time'])) if closing_data else None
        
        return opening_time, closing_time
    
    def calculate_working_time(self, hour_data, opening_time):
        """计算工作时间和加班时间的commit比例"""
        if not opening_time or not hour_data:
            # 如果没有识别出工作时间，使用简单的启发式方法
            # 假设9-18点为工作时间
            total_count = sum(item['count'] for item in hour_data)
            working_time = [item for item in hour_data if 9 <= int(item['time']) <= 18]
            working_else_time = [item for item in hour_data if item not in working_time]
            
            working_time_count = sum(item['count'] for item in working_time)
            working_else_time_count = sum(item['count'] for item in working_else_time)
            
            work_hour_pl = [
                {"time": "工作", "count": working_time_count},
                {"time": "加班", "count": working_else_time_count}
            ]
            return work_hour_pl, working_time_count, working_else_time_count
        
        opening_hour = int(opening_time['time'])
        
        # 工作时间：从开工时间算起的9小时
        working_time = [item for item in hour_data if opening_hour <= int(item['time']) <= opening_hour + 9]
        working_else_time = [item for item in hour_data if item not in working_time]
        
        working_time_count = sum(item['count'] for item in working_time)
        working_else_time_count = sum(item['count'] for item in working_else_time)
        
        work_hour_pl = [
            {"time": "工作", "count": working_time_count},
            {"time": "加班", "count": working_else_time_count}
        ]
        
        return work_hour_pl, working_time_count, working_else_time_count
    
    def calculate_week_type(self, week_data):
        """计算每周工作天数类型"""
        total_count = sum(item['count'] for item in week_data)
        if total_count == 0:
            return 5, []
        
        # 工作日（周一到周五）
        workday_count = sum(week_data[i]['count'] for i in range(5))
        # 周末（周六和周日）
        weekend_count = sum(week_data[i]['count'] for i in range(5, 7))
        
        workday_ratio = (workday_count / total_count) * 100
        
        # 判断工作天数类型
        if workday_ratio >= 90:
            work_days = 5
        elif workday_ratio >= 85:
            work_days = 6
        elif workday_ratio >= 79:
            work_days = 6  # 大小周
        elif workday_ratio >= 72:
            work_days = 7
        else:
            work_days = 7  # 周末也在干活
        
        work_week_pl = [
            {"time": "工作日", "count": workday_count},
            {"time": "周末", "count": weekend_count}
        ]
        
        return work_days, work_week_pl
    
    def calculate_996_index(self, work_hour_pl, work_week_pl, hour_data):
        """计算996指数"""
        # 检查数据有效性
        if not work_hour_pl or len(work_hour_pl) < 2 or not work_week_pl or len(work_week_pl) < 2:
            return 0, 0, False
        
        y = work_hour_pl[0]['count']  # 正常工作时间commit数
        x = work_hour_pl[1]['count']  # 加班时间commit数
        m = work_week_pl[0]['count']  # 工作日commit数
        n = work_week_pl[1]['count']  # 周末commit数
        
        total_count = y + x
        if total_count == 0:
            return 0, 0, False
        
        # 修正后的加班commit数量
        overtime_amend_count = round(x + (y * n) / (m + n) if (m + n) > 0 else x)
        
        # 加班commit百分比
        overtime_ratio = math.ceil((overtime_amend_count / total_count) * 100)
        
        # 特殊处理低加班且数据量不足的情况
        if overtime_ratio == 0 and len(hour_data) < 9:
            average_commit = total_count / len(hour_data) if len(hour_data) > 0 else 0
            mock_total_count = average_commit * 9
            if mock_total_count > 0:
                overtime_ratio = math.ceil((total_count / mock_total_count) * 100) - 100
        
        # 996指数 = 加班比例 * 3
        index_996 = overtime_ratio * 3
        
        # 判断是否为标准项目
        is_standard = index_996 < 200 and total_count > 50
        
        return index_996, overtime_ratio, is_standard
    
    def get_index_description(self, index_996):
        """根据996指数返回描述"""
        descriptions = {
            'excellent': ['令人羡慕的工作', '恭喜，你们没有福报', '你就是搬砖界的欧皇吧'],
            'good': ['你还有剩余价值'],
            'medium': ['加油，老板的法拉利靠你了'],
            'bad': ['你的福报已经修满了'],
            'terrible': ['你们想必就是卷王中的卷王吧']
        }
        
        if index_996 <= 10:
            return descriptions['excellent'][0]
        elif 10 < index_996 <= 50:
            return descriptions['good'][0]
        elif 50 < index_996 <= 90:
            return descriptions['medium'][0]
        elif 90 < index_996 <= 110:
            return descriptions['bad'][0]
        else:
            return descriptions['terrible'][0]
    
    def analyze(self):
        """执行完整的分析流程"""
        # 如果是远程仓库，先克隆
        if self.remote_url:
            self.clone_remote_repo()
        
        print(f"正在分析 Git 项目...")
        print(f"统计时间范围：{self.start_date} 至 {self.end_date}")
        
        # 获取统计数据
        hour_data = self.get_hour_stats()
        week_data = self.get_week_stats()
        
        total_count = sum(item['count'] for item in hour_data)
        
        if total_count == 0:
            print("错误：未找到任何commit记录")
            sys.exit(1)
        
        print(f"总 commit 数: {total_count}")
        
        # 计算工作时间范围
        opening_time, closing_time = self.calculate_work_time_range(hour_data)
        
        # 计算工作/加班时间
        work_hour_pl, _, _ = self.calculate_working_time(hour_data, opening_time)
        
        # 计算每周工作天数
        work_days, work_week_pl = self.calculate_week_type(week_data)
        
        # 计算996指数
        index_996, overtime_ratio, is_standard = self.calculate_996_index(
            work_hour_pl, work_week_pl, hour_data
        )
        
        # 构建结果对象
        opening_hour = int(opening_time['time']) if opening_time else None
        closing_hour = int(closing_time['time']) if closing_time else None
        
        result = {
            'start_date': self.start_date,
            'end_date': self.end_date,
            'total_count': total_count,
            'hour_data': hour_data,
            'week_data': week_data,
            'work_hour_pl': work_hour_pl,
            'work_week_pl': work_week_pl,
            'opening_hour': opening_hour,
            'closing_hour': closing_hour % 12 if closing_hour else None,
            'work_days': work_days,
            'index_996': index_996,
            'overtime_ratio': overtime_ratio,
            'is_standard': is_standard,
            'description': self.get_index_description(index_996)
        }
        
        return result


class MultiRepoAnalyzer:
    """
    多仓库批量分析器
    循环分析多个仓库，合并统计数据，计算汇总指标
    """
    
    def __init__(self, repo_list, start_date=None, end_date=None, author=None, project_name=None):
        """
        Args:
            repo_list: [{'path': '...', 'type': 'local'/'remote'}, ...]
            start_date: 起始日期
            end_date: 结束日期
            author: 作者过滤
            project_name: 汇总项目名称
        """
        self.repo_list = repo_list
        self.start_date = start_date
        self.end_date = end_date
        self.author = author
        self.project_name = project_name or self.generate_default_name()
        self.analyzers = []  # 保存每个仓库的分析器实例
    
    def generate_default_name(self):
        """生成默认的项目名称"""
        if len(self.repo_list) == 1:
            # 单仓库，使用仓库名
            path = self.repo_list[0]['path']
            if self.repo_list[0]['type'] == 'remote':
                # 从URL提取名称
                match = re.search(r'[:/]([^/]+/[^/]+?)(?:\.git)?/?$', path)
                if match:
                    return match.group(1).replace('/', '-')
            return os.path.basename(os.path.abspath(path))
        else:
            # 多仓库，使用 multi-project 前缀
            return f"multi-project-{len(self.repo_list)}-repos"
    
    def analyze(self):
        """
        循环分析每个仓库，合并结果
        
        Returns:
            dict: 汇总结果字典（结构与单仓库兼容，但新增汇总相关字段）
        """
        print(f"\n{'='*60}")
        print(f"多仓库汇总分析: {self.project_name}")
        print(f"共 {len(self.repo_list)} 个仓库")
        print(f"{'='*60}\n")
        
        # 1. 初始化汇总容器
        merged_hour_data = defaultdict(int)  # {hour: count}
        merged_week_data = defaultdict(int)  # {weekday: count}
        repo_results = []  # 每个仓库的详细结果
        failed_repos = []  # 失败的仓库
        
        # 2. 循环分析每个仓库
        for idx, repo_info in enumerate(self.repo_list, 1):
            repo_path = repo_info['path']
            repo_type = repo_info['type']
            
            print(f"[{idx}/{len(self.repo_list)}] 分析仓库: {repo_path}")
            
            try:
                # 创建单仓库分析器
                if repo_type == 'remote':
                    analyzer = Code996Analyzer(
                        start_date=self.start_date,
                        end_date=self.end_date,
                        author=self.author,
                        repo_path='.',
                        remote_url=repo_path
                    )
                else:
                    analyzer = Code996Analyzer(
                        start_date=self.start_date,
                        end_date=self.end_date,
                        author=self.author,
                        repo_path=repo_path,
                        remote_url=None
                    )
                
                # 保存分析器实例（用于后续清理）
                self.analyzers.append(analyzer)
                
                # 执行单仓库分析
                result = analyzer.analyze()
                
                # 获取仓库名称
                repo_name = analyzer.get_project_name()
                
                # 收集元信息
                repo_results.append({
                    'name': repo_name,
                    'path': repo_path,
                    'type': repo_type,
                    'result': result
                })
                
                # 合并小时统计数据
                for item in result['hour_data']:
                    merged_hour_data[item['time']] += item['count']
                
                # 合并星期统计数据
                for item in result['week_data']:
                    merged_week_data[item['time']] += item['count']
                
                print(f"    ✓ 完成 (commit数: {result['total_count']})")
                
            except Exception as e:
                print(f"    ✗ 失败: {e}", file=sys.stderr)
                failed_repos.append({
                    'path': repo_path,
                    'error': str(e)
                })
                continue
        
        # 检查是否所有仓库都失败了
        if not repo_results:
            print("\n错误: 所有仓库分析都失败了", file=sys.stderr)
            sys.exit(1)
        
        # 如果有失败的仓库，显示警告
        if failed_repos:
            print(f"\n⚠️  警告: {len(failed_repos)} 个仓库分析失败:")
            for failed in failed_repos:
                print(f"   - {failed['path']}: {failed['error']}")
        
        # 3. 将合并数据转换为标准格式
        # 小时数据：确保按小时排序
        hour_data = [
            {'time': hour, 'count': merged_hour_data[hour]}
            for hour in sorted(merged_hour_data.keys())
        ]
        
        # 星期数据：保持固定顺序
        week_labels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        week_data = [
            {'time': label, 'count': merged_week_data.get(label, 0)}
            for label in week_labels
        ]
        
        # 4. 对合并数据计算汇总指标（复用现有函数）
        total_count = sum(merged_hour_data.values())
        
        # 计算工作时间范围
        opening_time, closing_time = self.calculate_work_time_range(hour_data)
        
        # 计算工作/加班时间
        work_hour_pl, _, _ = self.calculate_working_time(hour_data, opening_time)
        
        # 计算每周工作天数
        work_days, work_week_pl = self.calculate_week_type(week_data)
        
        # 计算996指数
        index_996, overtime_ratio, is_standard = self.calculate_996_index(
            work_hour_pl, work_week_pl, hour_data
        )
        
        # 获取描述
        description = self.get_index_description(index_996)
        
        # 5. 构建汇总结果
        opening_hour = int(opening_time['time']) if opening_time else None
        closing_hour = int(closing_time['time']) if closing_time else None
        
        aggregate_result = {
            # 基本信息
            'start_date': self.start_date or "2022-01-01",
            'end_date': self.end_date or datetime.now().strftime("%Y-%m-%d"),
            'total_count': total_count,
            
            # 统计数据（与单仓库格式一致）
            'hour_data': hour_data,
            'week_data': week_data,
            'work_hour_pl': work_hour_pl,
            'work_week_pl': work_week_pl,
            
            # 工作时间特征
            'opening_hour': opening_hour,
            'closing_hour': closing_hour % 12 if closing_hour else None,
            'work_days': work_days,
            
            # 996指标
            'index_996': index_996,
            'overtime_ratio': overtime_ratio,
            'is_standard': is_standard,
            'description': description,
            
            # 多仓库特有字段 ⭐
            'is_aggregate': True,  # 标记为汇总模式
            'project_name': self.project_name,
            'repo_count': len(repo_results),
            'repo_results': repo_results,
            'failed_count': len(failed_repos)
        }
        
        return aggregate_result
    
    def calculate_work_time_range(self, hour_data):
        """计算工作时间范围（复用Code996Analyzer的算法）"""
        if not hour_data:
            return None, None
        
        total_count = sum(item['count'] for item in hour_data)
        if total_count == 0:
            return None, None
        
        quadratic_value = sum(item['count'] ** 2 for item in hour_data) / len(hour_data)
        standard_value = math.sqrt(quadratic_value)
        
        work_hours = [item for item in hour_data if item['count'] / standard_value >= 0.45]
        
        opening_data = [item for item in work_hours if 8 <= int(item['time']) <= 12]
        closing_data = [item for item in work_hours if 17 <= int(item['time']) <= 23]
        
        opening_time = min(opening_data, key=lambda x: int(x['time'])) if opening_data else None
        closing_time = max(closing_data, key=lambda x: int(x['time'])) if closing_data else None
        
        return opening_time, closing_time
    
    def calculate_working_time(self, hour_data, opening_time):
        """计算工作时间和加班时间（复用Code996Analyzer的算法）"""
        if not opening_time or not hour_data:
            total_count = sum(item['count'] for item in hour_data)
            working_time = [item for item in hour_data if 9 <= int(item['time']) <= 18]
            working_else_time = [item for item in hour_data if item not in working_time]
            
            working_time_count = sum(item['count'] for item in working_time)
            working_else_time_count = sum(item['count'] for item in working_else_time)
            
            work_hour_pl = [
                {"time": "工作", "count": working_time_count},
                {"time": "加班", "count": working_else_time_count}
            ]
            return work_hour_pl, working_time_count, working_else_time_count
        
        opening_hour = int(opening_time['time'])
        
        working_time = [item for item in hour_data if opening_hour <= int(item['time']) <= opening_hour + 9]
        working_else_time = [item for item in hour_data if item not in working_time]
        
        working_time_count = sum(item['count'] for item in working_time)
        working_else_time_count = sum(item['count'] for item in working_else_time)
        
        work_hour_pl = [
            {"time": "工作", "count": working_time_count},
            {"time": "加班", "count": working_else_time_count}
        ]
        
        return work_hour_pl, working_time_count, working_else_time_count
    
    def calculate_week_type(self, week_data):
        """计算每周工作天数（复用Code996Analyzer的算法）"""
        total_count = sum(item['count'] for item in week_data)
        if total_count == 0:
            return 5, []
        
        workday_count = sum(week_data[i]['count'] for i in range(5))
        weekend_count = sum(week_data[i]['count'] for i in range(5, 7))
        
        workday_ratio = (workday_count / total_count) * 100
        
        if workday_ratio >= 90:
            work_days = 5
        elif workday_ratio >= 85:
            work_days = 6
        elif workday_ratio >= 79:
            work_days = 6
        elif workday_ratio >= 72:
            work_days = 7
        else:
            work_days = 7
        
        work_week_pl = [
            {"time": "工作日", "count": workday_count},
            {"time": "周末", "count": weekend_count}
        ]
        
        return work_days, work_week_pl
    
    def calculate_996_index(self, work_hour_pl, work_week_pl, hour_data):
        """计算996指数（复用Code996Analyzer的算法）"""
        if not work_hour_pl or len(work_hour_pl) < 2 or not work_week_pl or len(work_week_pl) < 2:
            return 0, 0, False
        
        y = work_hour_pl[0]['count']
        x = work_hour_pl[1]['count']
        m = work_week_pl[0]['count']
        n = work_week_pl[1]['count']
        
        total_count = y + x
        if total_count == 0:
            return 0, 0, False
        
        overtime_amend_count = round(x + (y * n) / (m + n) if (m + n) > 0 else x)
        overtime_ratio = math.ceil((overtime_amend_count / total_count) * 100)
        
        if overtime_ratio == 0 and len(hour_data) < 9:
            average_commit = total_count / len(hour_data) if len(hour_data) > 0 else 0
            mock_total_count = average_commit * 9
            if mock_total_count > 0:
                overtime_ratio = math.ceil((total_count / mock_total_count) * 100) - 100
        
        index_996 = overtime_ratio * 3
        
        # 多仓库汇总通常commit数量较多，is_standard判断更宽松
        is_standard = index_996 < 200 and total_count > 30
        
        return index_996, overtime_ratio, is_standard
    
    def get_index_description(self, index_996):
        """根据996指数返回描述（复用Code996Analyzer的逻辑）"""
        if index_996 <= 10:
            return '令人羡慕的工作'
        elif 10 < index_996 <= 50:
            return '你还有剩余价值'
        elif 50 < index_996 <= 90:
            return '加油，老板的法拉利靠你了'
        elif 90 < index_996 <= 110:
            return '你的福报已经修满了'
        else:
            return '你们想必就是卷王中的卷王吧'
    
    def cleanup(self):
        """清理所有分析器的临时文件"""
        for analyzer in self.analyzers:
            try:
                analyzer.cleanup()
            except Exception as e:
                print(f"警告: 清理临时文件失败: {e}", file=sys.stderr)


def generate_repo_list_html(repo_results, total_count):
    """
    生成参与仓库列表的 HTML 表格
    
    Args:
        repo_results: 仓库结果列表
        total_count: 总 commit 数
    
    Returns:
        str: HTML 表格代码
    """
    html = """
    <h2 class="title">📦 参与仓库列表</h2>
    <div class="table-wrapper">
        <table>
            <thead>
                <tr>
                    <th>仓库名称</th>
                    <th>来源类型</th>
                    <th>Commit 数</th>
                    <th>占比</th>
                    <th>996 指数</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for repo in repo_results:
        name = repo['name']
        repo_type = '🌐 远程' if repo['type'] == 'remote' else '📁 本地'
        count = repo['result']['total_count']
        ratio = round(count / total_count * 100, 1) if total_count > 0 else 0
        index = repo['result']['index_996']
        
        html += f"""
                <tr>
                    <td style="text-align: left;">{name}</td>
                    <td>{repo_type}</td>
                    <td>{count}</td>
                    <td>{ratio}%</td>
                    <td>{index}</td>
                </tr>
        """
    
    html += """
            </tbody>
        </table>
        <p style='margin-top: 10px; color: #999; font-size: 14px;'>* 汇总数据为所有仓库合并后计算得出</p>
    </div>
    """
    
    return html


def get_default_output_filename(project_name, is_aggregate=False):
    """生成默认的输出文件名"""
    # 获取当前时间
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d·%H-%M-%S")
    
    # 清理项目名（移除特殊字符）
    clean_name = re.sub(r'[<>:"/\\|?*]', '-', project_name)
    
    # 多仓库模式添加前缀标识
    if is_aggregate and not clean_name.startswith('multi-'):
        clean_name = f"multi-{clean_name}"
    
    # 生成文件名格式：项目名·时间戳-result.html
    filename = f"{clean_name}·{timestamp}-result.html"
    
    # 创建 report 目录
    report_dir = "report"
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)
    
    # 返回完整路径
    return os.path.join(report_dir, filename)


def generate_html(result, output_file=None, project_name=None):
    """生成HTML报告"""
    
    # 检测是否为汇总模式
    is_aggregate = result.get('is_aggregate', False)
    
    # 如果未指定输出文件，使用默认格式
    if not output_file:
        if not project_name:
            project_name = result.get('project_name', 'unknown-project')
        output_file = get_default_output_filename(project_name, is_aggregate)
    
    # 读取chart.xkcd库
    chart_xkcd_cdn = "https://cdn.jsdelivr.net/npm/chart.xkcd@1.1.13/dist/chart.xkcd.min.js"
    
    # 准备小时分布数据
    hour_labels = [item['time'] for item in result['hour_data']]
    hour_counts = [item['count'] for item in result['hour_data']]
    
    # 准备周分布数据
    week_labels = [item['time'] for item in result['week_data']]
    week_counts = [item['count'] for item in result['week_data']]
    
    # 工作/加班数据
    work_hour_labels = [item['time'] for item in result['work_hour_pl']]
    work_hour_counts = [item['count'] for item in result['work_hour_pl']]
    
    work_week_labels = [item['time'] for item in result['work_week_pl']]
    work_week_counts = [item['count'] for item in result['work_week_pl']]
    
    # 计算比例数据
    total_work_hour = sum(work_hour_counts)
    work_hour_percentages = [round(c / total_work_hour * 100, 1) if total_work_hour > 0 else 0 for c in work_hour_counts]
    
    total_work_week = sum(work_week_counts)
    work_week_percentages = [round(c / total_work_week * 100, 1) if total_work_week > 0 else 0 for c in work_week_counts]
    
    # 对比表格数据
    table_data = [
        {'type': '955', 'daily': '6.5', 'weekly': '32.5', 'overtime': '-5', 'ratio': '-11', 'index': '-33'},
        {'type': '965', 'daily': '7.5', 'weekly': '37.5', 'overtime': '0', 'ratio': '0', 'index': '0'},
        {'type': '966', 'daily': '7.5', 'weekly': '45', 'overtime': '7.5', 'ratio': '16', 'index': '48'},
        {'type': '995', 'daily': '9.5', 'weekly': '47.5', 'overtime': '10', 'ratio': '21', 'index': '63'},
        {'type': '996', 'daily': '9.5', 'weekly': '57', 'overtime': '19.5', 'ratio': '34', 'index': '100'},
        {'type': '997', 'daily': '9.5', 'weekly': '66.5', 'overtime': '29', 'ratio': '44', 'index': '130'},
        {'type': '9126', 'daily': '12.5', 'weekly': '75', 'overtime': '37.5', 'ratio': '50', 'index': '150'},
    ]
    
    working_type = f"{result['opening_hour'] or '?'}{result['closing_hour'] or '?'}{result['work_days'] or '?'}"
    
    # 计算当前项目的数据
    opening_hour = result['opening_hour'] if result['opening_hour'] else 9
    closing_hour = result['closing_hour'] if result['closing_hour'] else 18
    work_days = result['work_days'] if result['work_days'] else 5
    
    # 日均打卡时长
    attendance = closing_hour - opening_hour if closing_hour > opening_hour else 12 - opening_hour + closing_hour
    
    # 日均有效工作时间（减去休息时间）
    if closing_hour <= 19 or (closing_hour <= 7 and attendance <= 10):
        daily_work = attendance - 1.5  # 只休息中午
    else:
        daily_work = attendance - 2.5  # 加上晚餐休息
    
    # 确保合理值
    if daily_work < 0:
        daily_work = 0
    
    weekly_work = round(daily_work * work_days, 1)
    overtime = round((result['overtime_ratio'] * 0.01 * weekly_work), 1)
    
    # 添加当前项目到表格
    current_project = {
        'type': working_type,
        'daily': str(round(daily_work, 1)),
        'weekly': str(weekly_work),
        'overtime': str(overtime),
        'ratio': str(result['overtime_ratio']),
        'index': str(result['index_996'])
    }
    
    # 将当前项目插入到表格中，按996指数排序
    table_data.append(current_project)
    table_data = sorted(table_data, key=lambda x: float(x['index']))
    
    # 生成标题文本
    if is_aggregate:
        page_title = f"聚合项目：{result.get('project_name', 'Multi-Project')}（共 {result.get('repo_count', 0)} 个仓库）"
    else:
        page_title = "#CODE996 Result"
    
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code996 分析报告 - {project_name or 'Project'}</title>
    <script src="{chart_xkcd_cdn}"></script>
    <style>
        /* 字体定义 */
        @font-face {{
            font-family: 'vcr-osd';
            src: url('https://fastly.jsdelivr.net/gh/hellodigua/cdn/fonts/vcr-osd.ttf');
            font-display: swap;
        }}
        
        @font-face {{
            font-family: 'Pixel';
            src: url('https://fastly.jsdelivr.net/gh/hellodigua/cdn/fonts/zpix.woff2') format('woff2');
            font-display: swap;
        }}
        
        @font-face {{
            font-family: 'xkcd';
            src: url('https://fastly.jsdelivr.net/gh/hellodigua/cdn/fonts/zpix.woff2') format('woff2');
            font-display: swap;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            background-color: #212121;
            color: #ccc;
            font-family: 'Pixel', Helvetica Neue, Helvetica, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Arial, sans-serif;
            font-size: 16px;
            line-height: 1.75;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .top-bar {{
            padding: 40px 0;
            background: #2a2a2a;
            margin-bottom: 40px;
        }}
        
        .top-bar h1 {{
            font-family: 'vcr-osd', monospace;
            color: #999;
            font-size: 2em;
            font-weight: normal;
            text-shadow: 6px 6px 0px rgba(0, 0, 0, 0.2);
        }}
        
        .top-result {{
            margin-bottom: 60px;
        }}
        
        .top-result h1 {{
            font-size: 2em;
            color: #de335e;
            text-shadow: 6px 6px 0px rgba(0, 0, 0, 0.2);
            margin-bottom: 40px;
        }}
        
        .result-line {{
            display: flex;
            align-items: flex-start;
            flex-wrap: wrap;
        }}
        
        .score-box {{
            margin-right: 60px;
            margin-bottom: 20px;
        }}
        
        .score-number {{
            background-color: #de335e;
            color: #fff;
            font-size: 6em;
            text-shadow: 10px 10px 0px rgba(0, 0, 0, 0.2);
            box-shadow: 10px 10px 0px rgba(0, 0, 0, 0.2);
            font-family: 'vcr-osd', monospace;
            line-height: 1;
            padding: 30px;
            display: inline-block;
        }}
        
        .content {{
            flex: 1;
            min-width: 300px;
        }}
        
        .content p {{
            margin-bottom: 15px;
            font-size: 1.1em;
        }}
        
        .p1 {{
            color: #de335e;
            font-size: 1.5em;
            font-weight: bold;
        }}
        
        .p2 {{
            color: #999;
            font-size: 0.9em;
            margin-left: 8px;
        }}
        
        .exp {{
            margin-top: 40px;
            font-size: 0.85em;
            opacity: 0.6;
        }}
        
        .section {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 40px;
            flex-wrap: wrap;
        }}
        
        .item {{
            width: 48%;
            min-width: 300px;
            background-color: #2a2a2a;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 10px 10px 0px rgba(0, 0, 0, 0.1);
        }}
        
        .item svg {{
            background-color: #2a2a2a;
        }}
        
        .item h2 {{
            font-size: 1.2em;
            margin-bottom: 20px;
            font-weight: normal;
            color: #fff;
        }}
        
        .chart-container {{
            width: 100%;
            height: 300px;
            position: relative;
        }}
        
        .chart-container svg {{
            width: 100%;
            height: 100%;
        }}
        
        h2.title {{
            font-size: 1.5em;
            margin: 40px 0 20px 0;
            color: #fff;
        }}
        
        .table-wrapper {{
            overflow-x: auto;
            margin-bottom: 40px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            background-color: #2a2a2a;
        }}
        
        th, td {{
            padding: 15px;
            text-align: center;
            border-bottom: 1px solid #555;
        }}
        
        th {{
            border-bottom: 2px solid #999;
            font-weight: bold;
        }}
        
        .active {{
            color: #de335e;
            font-weight: bold;
        }}
        
        .notice {{
            background-color: #2a2a2a;
            padding: 20px;
            margin: 40px 0;
        }}
        
        .notice h2 {{
            margin-bottom: 15px;
        }}
        
        .notice p {{
            margin-bottom: 10px;
            opacity: 0.8;
        }}
        
        @media screen and (max-width: 768px) {{
            .result-line {{
                flex-direction: column;
            }}
            
            .score-box {{
                margin-right: 0;
                margin-bottom: 30px;
            }}
            
            .section {{
                flex-direction: column;
            }}
            
            .item {{
                width: 100%;
            }}
        }}
    </style>
</head>
<body>
    <div class="top-bar">
        <div class="container">
            <h1>{page_title}</h1>
        </div>
    </div>
    
    <div class="container">
        <div class="top-result">
            {"<h1>该项目的 996 指数是：</h1>" if result['is_standard'] else ""}
            <div class="result-line">
                {"<div class='score-box'><div class='score-number'>" + str(result['index_996']) + "</div></div>" if result['is_standard'] else ""}
                <div class="content">
                    {"<p>推测你们的工作时间类型为：<span class='p1'>" + working_type + "</span> <span class='p2'>(早 " + str(result['opening_hour'] or '?') + " 晚 " + str(result['closing_hour'] or '?') + " 一周 " + str(result['work_days']) + " 天)</span></p>" if result['is_standard'] else ""}
                    {"<p>推测你们的加班时间占比为：<span class='p1'>" + str(result['overtime_ratio']) + "%</span>" + (" <span class='p2'>(工作不饱和)</span>" if result['index_996'] < 0 else "") + "</p>" if result['is_standard'] else ""}
                    {"<p><span class='p1'>" + ("该项目的 commit 数量过少，只显示基本信息" if result['total_count'] <= 50 else "该项目为开源项目，只显示基本信息") + "</span></p>" if not result['is_standard'] else ""}
                    <p>总 commit 数：<span class="p1">{result['total_count']}</span></p>
                    <p>分析时间段：<span class="p1">{result['start_date']} ∼ {result['end_date']}</span></p>
                </div>
            </div>
            {"<p class='exp'>996 指数：为 0 则不加班，值越大代表加班越严重，996 工作制对应的值为 100，负值说明工作非常轻松。<a href='#compare-table' style='color: #de335e;'>具体可参考下方表格</a></p>" if result['is_standard'] else ""}
        </div>
        
        {generate_repo_list_html(result['repo_results'], result['total_count']) if is_aggregate else ""}
        
        <div class="charts">
            <div class="section">
                <div class="item">
                    <h2>按小时 commit 分布</h2>
                    <div class="chart-container">
                        <svg id="hourChart"></svg>
                    </div>
                </div>
                <div class='item'><h2>加班/工作 commit 占比（按小时）</h2><div class='chart-container'><svg id='hourPieChart'></svg></div></div>
            </div>
            
            <div class="section">
                <div class="item">
                    <h2>按天 commit 分布</h2>
                    <div class="chart-container">
                        <svg id="weekChart"></svg>
                    </div>
                </div>
                <div class='item'><h2>加班/工作 commit 占比（按天）</h2><div class='chart-container'><svg id='weekPieChart'></svg></div></div>
            </div>
        </div>
        
        <h2 class="title" id="compare-table">工作时间参照表：</h2>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>时间类型</th>
                        <th>日均工作时长</th>
                        <th>每周工作时长</th>
                        <th>每周加班时长</th>
                        <th>加班时间占比</th>
                        <th>996指数</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join([f"<tr class='{'active' if item['type'] == working_type else ''}'><td>{item['type']}</td><td>{item['daily']}h</td><td>{item['weekly']}h</td><td>{item['overtime']}h</td><td>{item['ratio']}%</td><td>{item['index']}</td></tr>" for item in table_data])}
                </tbody>
            </table>
            <p style='margin-top: 10px; color: #999; font-size: 14px;'>* 高亮行为该项目的估算指标</p>
        </div>
        
        <div class="notice">
            <h2 class="title">⚠️ 注意事项：</h2>
            {f"<p>📊 本报告为 <strong>{result.get('repo_count', 0)} 个仓库</strong>的汇总分析，数据已合并计算</p>" if is_aggregate else ""}
            {f"<p>🌍 多仓库数据可能来自不同时区、不同团队，存在一定误差</p>" if is_aggregate else ""}
            <p>1. 分析结果仅供参考，不代表任何建议</p>
            <p>2. 原始分析数据基于 Git commit 时间，可能与实际工作时间有偏差</p>
            <p>3. 请勿用于正式场合</p>
        </div>
    </div>
    
    <script>
        // 等待DOM和chart.xkcd库加载完成
        window.addEventListener('load', function() {{
            try {{
                // 确保chartXkcd已加载
                if (typeof chartXkcd === 'undefined') {{
                    console.error('chart.xkcd库未加载');
                    return;
                }}
                
                // 小时分布图
                const hourChartEl = document.getElementById('hourChart');
                if (hourChartEl) {{
                    new chartXkcd.Bar(hourChartEl, {{
                        data: {{
                            labels: {json.dumps(hour_labels)},
                            datasets: [{{
                                data: {json.dumps(hour_counts)}
                            }}]
                        }},
                        options: {{
                            backgroundColor: '#2a2a2a',
                            strokeColor: '#fff',
                            unxkcdify: false
                        }}
                    }});
                }}
                
                // 周分布图
                const weekChartEl = document.getElementById('weekChart');
                if (weekChartEl) {{
                    new chartXkcd.Bar(weekChartEl, {{
                        data: {{
                            labels: {json.dumps(week_labels)},
                            datasets: [{{
                                data: {json.dumps(week_counts)}
                            }}]
                        }},
                        options: {{
                            backgroundColor: '#2a2a2a',
                            strokeColor: '#fff',
                            unxkcdify: false
                        }}
                    }});
                }}
                
                // 工作/加班占比饼图（按小时）
                const hourPieChartEl = document.getElementById('hourPieChart');
                if (hourPieChartEl) {{
                    new chartXkcd.Pie(hourPieChartEl, {{
                        data: {{
                            labels: {json.dumps(work_hour_labels)},
                            datasets: [{{
                                data: {json.dumps(work_hour_counts)}
                            }}]
                        }},
                        options: {{
                            backgroundColor: '#2a2a2a',
                            strokeColor: '#fff'
                        }}
                    }});
                }}
                
                // 工作/加班占比饼图（按天）
                const weekPieChartEl = document.getElementById('weekPieChart');
                if (weekPieChartEl) {{
                    new chartXkcd.Pie(weekPieChartEl, {{
                        data: {{
                            labels: {json.dumps(work_week_labels)},
                            datasets: [{{
                                data: {json.dumps(work_week_counts)}
                            }}]
                        }},
                        options: {{
                            backgroundColor: '#2a2a2a',
                            strokeColor: '#fff'
                        }}
                    }});
                }}
            }} catch (error) {{
                console.error('图表初始化错误:', error);
            }}
        }});
    </script>
</body>
</html>
"""
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Code996 本地版 - 统计 Git 项目的 commit 时间分布',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析单个本地项目
  python code996_local.py
  python code996_local.py --start 2023-01-01 --end 2023-12-31
  python code996_local.py --author "yourname" --output my_report.html
  
  # 分析单个远程项目
  python code996_local.py --url https://github.com/user/repo
  python code996_local.py --url https://github.com/user/repo --author "yourname"
  
  # 多仓库汇总分析 ⭐ 新功能
  python code996_local.py --repos /path/repo1,/path/repo2,/path/repo3 --project-name "Team Backend"
  python code996_local.py --urls https://github.com/org/repo1,https://github.com/org/repo2
  python code996_local.py --input-file repos.txt --project-name "Q4 Projects"
        """
    )
    
    parser.add_argument('--start', '-s', default=None,
                        help='分析的起始时间 (格式: YYYY-MM-DD)')
    parser.add_argument('--end', '-e', default=None,
                        help='分析的结束时间 (格式: YYYY-MM-DD)')
    parser.add_argument('--author', '-a', default=None,
                        help='指定提交用户 (name 或 email)')
    
    # 单仓库参数（支持多次传入）
    parser.add_argument('--repo', '-r', action='append', default=None,
                        help='Git 仓库路径 (可多次使用)')
    parser.add_argument('--url', '-u', action='append', default=None,
                        help='远程 Git 仓库 URL (可多次使用)')
    
    # 多仓库参数 ⭐ 新增
    parser.add_argument('--repos', default=None,
                        help='逗号分隔的本地仓库路径列表 (如: /path1,/path2)')
    parser.add_argument('--urls', default=None,
                        help='逗号分隔的远程仓库URL列表 (如: url1,url2)')
    parser.add_argument('--input-file', default=None,
                        help='从文件读取仓库列表 (每行一个，支持 # 注释)')
    parser.add_argument('--project-name', default=None,
                        help='多仓库汇总项目的显示名称')
    
    parser.add_argument('--output', '-o', default=None,
                        help='输出HTML文件名 (默认: report/项目名·时间戳-result.html)')
    parser.add_argument('--no-browser', action='store_true',
                        help='不自动打开浏览器')
    
    args = parser.parse_args()
    
    # 验证参数
    validate_repo_params(args)
    
    # 解析仓库列表
    repo_list = parse_repo_list(args)
    
    # 判断模式：单仓库 or 多仓库
    is_multi_repo = len(repo_list) > 1 or args.project_name or args.repos or args.urls or args.input_file
    
    analyzer_instance = None
    multi_analyzer_instance = None
    
    try:
        if is_multi_repo:
            # ========== 多仓库模式 ==========
            print("\n🚀 启动多仓库汇总分析模式")
            
            multi_analyzer_instance = MultiRepoAnalyzer(
                repo_list=repo_list,
                start_date=args.start,
                end_date=args.end,
                author=args.author,
                project_name=args.project_name
            )
            
            # 执行分析
            result = multi_analyzer_instance.analyze()
            project_name = result['project_name']
            
            # 生成HTML报告
            output_file = generate_html(result, args.output, project_name)
            
            # 打印结果摘要
            print("\n" + "="*60)
            print("📊 多仓库汇总分析结果")
            print("="*60)
            print(f"项目名称: {project_name}")
            print(f"仓库数量: {result['repo_count']}")
            print(f"总 commit 数: {result['total_count']}")
            
            if result['is_standard']:
                print(f"996 指数: {result['index_996']}")
                print(f"工作类型: {result['opening_hour'] or '?'}{result['closing_hour'] or '?'}{result['work_days']}")
                print(f"加班占比: {result['overtime_ratio']}%")
                print(f"评价: {result['description']}")
            else:
                if result['total_count'] <= 30:
                    print("汇总 commit 数量较少，只显示基本信息")
                else:
                    print("显示基本信息")
            
            if result.get('failed_count', 0) > 0:
                print(f"⚠️  失败仓库: {result['failed_count']} 个")
            
            print("="*60)
            
        else:
            # ========== 单仓库模式（向后兼容）==========
            repo_info = repo_list[0]
            
            analyzer_instance = Code996Analyzer(
                start_date=args.start,
                end_date=args.end,
                author=args.author,
                repo_path=repo_info['path'] if repo_info['type'] == 'local' else '.',
                remote_url=repo_info['path'] if repo_info['type'] == 'remote' else None
            )
            
            # 执行分析
            result = analyzer_instance.analyze()
            
            # 获取项目名称
            project_name = analyzer_instance.get_project_name()
            
            # 生成HTML报告
            output_file = generate_html(result, args.output, project_name)
            
            # 打印结果摘要
            print("\n" + "="*50)
            print("分析结果摘要")
            print("="*50)
            print(f"项目名称: {project_name}")
            if result['is_standard']:
                print(f"996指数: {result['index_996']}")
                print(f"工作类型: {result['opening_hour'] or '?'}{result['closing_hour'] or '?'}{result['work_days']}")
                print(f"加班占比: {result['overtime_ratio']}%")
                print(f"评价: {result['description']}")
            else:
                if result['total_count'] <= 50:
                    print("该项目的 commit 数量过少，只显示基本信息")
                else:
                    print("该项目为开源项目，只显示基本信息")
            print(f"总commit数: {result['total_count']}")
            print("="*50)
        
        # ========== 共通部分：显示报告信息并打开浏览器 ==========
        abs_path = os.path.abspath(output_file)
        print(f"\n✓ 报告已生成")
        print(f"📄 文件名: {os.path.basename(output_file)}")
        print(f"📁 保存位置: {abs_path}")
        
        # 打开浏览器
        if not args.no_browser:
            print(f"\n正在打开浏览器...")
            webbrowser.open(f'file://{abs_path}')
    
    finally:
        # 清理临时文件
        if analyzer_instance:
            analyzer_instance.cleanup()
        if multi_analyzer_instance:
            multi_analyzer_instance.cleanup()


if __name__ == '__main__':
    main()

