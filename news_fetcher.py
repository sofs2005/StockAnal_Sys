# news_fetcher.py
# -*- coding: utf-8 -*-
"""
智能分析系统（股票） - 新闻数据获取模块
功能: 获取财联社电报新闻数据并缓存到本地，避免重复内容
"""

import os
import json
import logging
import time
import hashlib
import shutil
import glob
from datetime import datetime, timedelta, date
import akshare as ak
import pandas as pd

# 设置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('news_fetcher')

# 自定义JSON编码器，处理日期类型
class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if pd.isna(obj):  # 处理pandas中的NaN
            return None
        return super(DateEncoder, self).default(obj)

class NewsFetcher:
    def __init__(self, save_dir="data/news"):
        """初始化新闻获取器"""
        self.save_dir = save_dir
        # 确保保存目录存在
        os.makedirs(self.save_dir, exist_ok=True)
        self.last_fetch_time = None

        # 哈希集合用于快速判断新闻是否已存在
        self.news_hashes = set()
        # 加载已有的新闻哈希
        self._load_existing_hashes()

    def _load_existing_hashes(self):
        """加载已有文件中的新闻哈希值"""
        try:
            # 获取最近3天的文件来加载哈希值
            today = datetime.now()
            for i in range(3):  # 检查今天和前两天的数据
                date = today - timedelta(days=i)
                date_str = date.strftime('%Y%m%d')
                # 直接构建文件名，避免使用get_news_filename方法
                import os
                filename = os.path.join(self.save_dir, f"news_{date_str}.json")

                if os.path.exists(filename):
                    # 尝试不同的编码方式读取文件
                    encodings_to_try = ['utf-8', 'gbk', 'gb2312', 'latin1']
                    for encoding in encodings_to_try:
                        try:
                            with open(filename, 'r', encoding=encoding) as f:
                                news_data = json.load(f)
                                for item in news_data:
                                    # 如果有哈希字段就直接使用，否则计算新的哈希
                                    if 'hash' in item:
                                        self.news_hashes.add(item['hash'])
                                    else:
                                        content_hash = self._calculate_hash(item['content'])
                                        self.news_hashes.add(content_hash)
                                logger.info(f"使用 {encoding} 编码成功加载文件 {filename}")
                                break  # 成功读取后跳出循环
                        except UnicodeDecodeError:
                            logger.warning(f"使用 {encoding} 编码读取文件 {filename} 失败，尝试其他编码")
                            continue
                        except json.JSONDecodeError:
                            logger.warning(f"文件 {filename} JSON格式错误，跳过加载哈希值")
                            break
                        except Exception as e:
                            logger.error(f"读取文件 {filename} 时出错: {str(e)}")
                            break

            logger.info(f"已加载 {len(self.news_hashes)} 条新闻哈希值")
        except Exception as e:
            logger.error(f"加载现有新闻哈希值时出错: {str(e)}")
            # 出错时清空哈希集合，保证程序可以继续运行
            self.news_hashes = set()

    def _calculate_hash(self, content):
        """计算新闻内容的哈希值"""
        # 使用MD5哈希算法计算内容的哈希值
        # 对于财经新闻，内容通常是唯一的标识，所以只对内容计算哈希
        return hashlib.md5(str(content).encode('utf-8')).hexdigest()

    def get_news_filename(self, date=None):
        """获取指定日期的新闻文件名"""
        # 导入全局模块
        import os

        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        else:
            date = date.strftime('%Y%m%d')

        # 确保目录存在
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)

        return os.path.join(self.save_dir, f"news_{date}.json")

    def fetch_and_save(self):
        """获取新闻并保存到JSON文件，避免重复内容"""
        try:
            # 获取当前时间
            now = datetime.now()

            # 调用AKShare API获取财联社电报数据
            logger.info("开始获取财联社电报数据")
            stock_info_global_cls_df = ak.stock_info_global_cls(symbol="全部")

            if stock_info_global_cls_df.empty:
                logger.warning("获取的财联社电报数据为空")
                return False

            # 打印DataFrame的信息和类型，帮助调试
            logger.info(f"获取的数据形状: {stock_info_global_cls_df.shape}")
            logger.info(f"数据列: {stock_info_global_cls_df.columns.tolist()}")
            logger.info(f"数据类型: \n{stock_info_global_cls_df.dtypes}")

            # 计数器
            total_count = 0
            new_count = 0

            # 转换为列表字典格式并添加哈希值
            news_list = []
            for _, row in stock_info_global_cls_df.iterrows():
                total_count += 1

                # 安全获取内容，确保为字符串
                content = str(row.get("内容", ""))

                # 计算内容哈希值
                content_hash = self._calculate_hash(content)

                # 检查是否已存在相同内容的新闻
                if content_hash in self.news_hashes:
                    continue  # 跳过已存在的新闻

                # 添加新的哈希值到集合
                self.news_hashes.add(content_hash)
                new_count += 1

                # 安全获取日期和时间，确保为字符串格式
                pub_date = row.get("发布日期", "")
                if isinstance(pub_date, (datetime, date)):
                    pub_date = pub_date.isoformat()
                else:
                    pub_date = str(pub_date)

                pub_time = row.get("发布时间", "")
                if isinstance(pub_time, (datetime, date)):
                    pub_time = pub_time.isoformat()
                else:
                    pub_time = str(pub_time)

                # 创建新闻项并添加哈希值
                news_item = {
                    "title": str(row.get("标题", "")),
                    "content": content,
                    "date": pub_date,
                    "time": pub_time,
                    "datetime": f"{pub_date} {pub_time}",
                    "fetch_time": now.strftime('%Y-%m-%d %H:%M:%S'),
                    "hash": content_hash  # 保存哈希值以便后续使用
                }
                news_list.append(news_item)

            # 如果没有新的新闻，直接返回
            if not news_list:
                logger.info(f"没有新的新闻数据需要保存 (共检查 {total_count} 条)")
                return True

            # 直接构建文件名，避免使用get_news_filename方法
            import os
            date_str = now.strftime('%Y%m%d')
            filename = os.path.join(self.save_dir, f"news_{date_str}.json")

            # 确保目录存在
            news_dir = os.path.dirname(filename)
            if not os.path.exists(news_dir):
                os.makedirs(news_dir, exist_ok=True)
                logger.info(f"创建新闻目录: {news_dir}")

            # 如果文件已存在，则合并新旧数据
            if os.path.exists(filename):
                existing_data = []
                file_read_success = False

                # 尝试不同的编码方式读取文件
                encodings_to_try = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin1']
                for encoding in encodings_to_try:
                    try:
                        with open(filename, 'r', encoding=encoding) as f:
                            file_content = f.read()
                            # 尝试解析JSON
                            existing_data = json.loads(file_content)
                            file_read_success = True
                            logger.info(f"成功使用 {encoding} 编码读取文件 {filename}")

                            # 如果文件不是UTF-8编码，尝试将其转换为UTF-8并保存
                            if encoding != 'utf-8' and encoding != 'utf-8-sig':
                                logger.info(f"文件 {filename} 使用的是 {encoding} 编码，将转换为 UTF-8")
                            break
                    except UnicodeDecodeError:
                        logger.warning(f"使用 {encoding} 编码读取文件 {filename} 失败，尝试其他编码")
                        continue
                    except json.JSONDecodeError:
                        logger.warning(f"文件 {filename} JSON格式错误，使用新数据替换")
                        break
                    except Exception as e:
                        logger.error(f"读取文件 {filename} 时出现未知错误: {str(e)}")
                        break

                # 如果所有编码方式都失败，尝试备份并重建文件
                if not file_read_success:
                    try:
                        # 创建备份文件
                        backup_filename = f"{filename}.corrupted.{int(time.time())}"
                        if os.path.exists(filename):
                            shutil.copy2(filename, backup_filename)
                            logger.info(f"已创建损坏文件备份: {backup_filename}")
                    except Exception as e:
                        logger.error(f"创建备份文件时出错: {str(e)}")

                    # 使用新数据
                    existing_data = []

                # 合并数据，已经确保news_list中的内容都是新的
                merged_news = existing_data + news_list
                # 按时间排序
                merged_news.sort(key=lambda x: x.get('datetime', ''), reverse=True)
            else:
                # 如果文件不存在，直接使用新数据
                merged_news = sorted(news_list, key=lambda x: x.get('datetime', ''), reverse=True)

            # 保存合并后的数据，使用自定义编码器处理日期
            try:
                # 确保目录存在
                import os
                news_dir = os.path.dirname(filename)
                if not os.path.exists(news_dir):
                    os.makedirs(news_dir, exist_ok=True)
                    logger.info(f"创建新闻目录: {news_dir}")

                # 直接写入文件，不使用临时文件
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(merged_news, f, ensure_ascii=False, indent=2, cls=DateEncoder)

                logger.info(f"成功保存新闻数据到文件: {filename}")
            except Exception as e:
                logger.error(f"保存新闻数据到文件 {filename} 时出错: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())

            logger.info(f"成功保存 {new_count} 条新闻数据 (共检查 {total_count} 条，过滤重复 {total_count - new_count} 条)")
            self.last_fetch_time = now
            return True

        except Exception as e:
            logger.error(f"获取或保存新闻数据时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())  # 打印完整的堆栈跟踪，便于调试
            return False

    def get_latest_news(self, days=1, limit=50):
        """获取最近几天的新闻数据，并去除重复项"""
        news_data = []
        today = datetime.now()
        # 记录已处理的日期，便于日志
        processed_dates = []

        # 获取指定天数内的所有新闻
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime('%Y%m%d')
            # 直接构建文件名，避免使用get_news_filename方法
            import os
            filename = os.path.join(self.save_dir, f"news_{date_str}.json")

            if os.path.exists(filename):
                file_loaded = False
                # 尝试不同的编码方式读取文件
                encodings_to_try = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin1']
                for encoding in encodings_to_try:
                    try:
                        with open(filename, 'r', encoding=encoding) as f:
                            file_content = f.read()
                            # 尝试解析JSON
                            data = json.loads(file_content)
                            news_data.extend(data)
                            processed_dates.append(date_str)
                            logger.info(f"已使用 {encoding} 编码加载 {date_str} 新闻数据 {len(data)} 条")
                            file_loaded = True

                            # 如果文件不是UTF-8编码，尝试将其转换为UTF-8并保存
                            if encoding != 'utf-8' and encoding != 'utf-8-sig':
                                try:
                                    # 直接写入文件，不使用临时文件
                                    with open(filename, 'w', encoding='utf-8') as tf:
                                        json.dump(data, tf, ensure_ascii=False, indent=2)
                                    logger.info(f"已将文件 {filename} 从 {encoding} 编码转换为 UTF-8 编码")
                                except Exception as e:
                                    logger.error(f"转换文件编码时出错: {str(e)}")

                            break
                    except UnicodeDecodeError:
                        logger.warning(f"使用 {encoding} 编码读取文件 {filename} 失败，尝试其他编码")
                        continue
                    except json.JSONDecodeError:
                        logger.warning(f"文件 {filename} JSON格式错误，跳过该文件")
                        break
                    except Exception as e:
                        logger.error(f"读取文件 {filename} 时出现未知错误: {str(e)}")
                        break

                # 如果所有编码方式都失败，尝试备份损坏文件
                if not file_loaded:
                    try:
                        # 创建备份文件
                        backup_filename = f"{filename}.corrupted.{int(time.time())}"
                        shutil.copy2(filename, backup_filename)
                        logger.info(f"已创建损坏文件备份: {backup_filename}")

                        # 创建空文件替换损坏文件
                        with open(filename, 'w', encoding='utf-8') as f:
                            json.dump([], f, ensure_ascii=False, indent=2)
                        logger.info(f"已创建空文件替换损坏文件: {filename}")
                    except Exception as e:
                        logger.error(f"创建备份文件时出错: {str(e)}")

                    logger.error(f"无法读取文件 {filename}，跳过该文件")
            else:
                logger.warning(f"日期 {date_str} 的新闻文件不存在: {filename}")

        # 排序前记录总数
        total_before_sort = len(news_data)

        # 去除重复项
        # 使用内容哈希或已有的哈希字段作为唯一标识
        unique_news = {}
        duplicate_count = 0

        for item in news_data:
            # 优先使用已有的哈希值，如果没有则计算内容哈希
            item_hash = item.get('hash')
            if not item_hash and 'content' in item:
                item_hash = self._calculate_hash(item['content'])

            # 如果是新的哈希值，则添加到结果中
            if item_hash and item_hash not in unique_news:
                unique_news[item_hash] = item
            else:
                duplicate_count += 1

        # 转换回列表并按时间排序
        deduplicated_news = list(unique_news.values())
        deduplicated_news.sort(key=lambda x: x.get('datetime', ''), reverse=True)

        # 限制返回条数
        result = deduplicated_news[:limit]

        logger.info(f"获取最近 {days} 天新闻(处理日期:{','.join(processed_dates)}), "
                    f"共 {total_before_sort} 条, 去重后 {len(deduplicated_news)} 条, "
                    f"移除重复 {duplicate_count} 条, 返回最新 {len(result)} 条")

        return result

# 单例模式的新闻获取器
news_fetcher = NewsFetcher()

def fetch_news_task():
    """执行新闻获取任务"""
    logger.info("开始执行新闻获取任务")
    news_fetcher.fetch_and_save()
    logger.info("新闻获取任务完成")

def start_news_scheduler():
    """启动新闻获取定时任务"""
    import threading
    import time

    def _run_scheduler():
        while True:
            try:
                fetch_news_task()
                # 等待10分钟
                time.sleep(600)
            except Exception as e:
                logger.error(f"定时任务执行出错: {str(e)}")
                time.sleep(60)  # 出错后等待1分钟再试

    # 创建并启动定时任务线程
    scheduler_thread = threading.Thread(target=_run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    logger.info("新闻获取定时任务已启动")

def clean_corrupted_news_files():
    """清理损坏的新闻文件，并创建备份"""

    logger.info("开始清理损坏的新闻文件")

    # 获取新闻文件目录
    news_dir = "data/news"
    if not os.path.exists(news_dir):
        os.makedirs(news_dir, exist_ok=True)
        logger.info(f"创建新闻目录: {news_dir}")
        return

    # 获取所有新闻文件
    news_files = glob.glob(os.path.join(news_dir, "news_*.json"))
    logger.info(f"找到 {len(news_files)} 个新闻文件")

    for file_path in news_files:
        try:
            # 尝试读取文件
            file_valid = False
            for encoding in ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin1']:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        file_content = f.read()
                        # 尝试解析JSON
                        json_data = json.loads(file_content)
                        file_valid = True
                        logger.info(f"文件 {file_path} 可以使用 {encoding} 编码正常读取")

                        # 如果文件不是UTF-8编码，尝试将其转换为UTF-8并保存
                        if encoding != 'utf-8' and encoding != 'utf-8-sig':
                            try:
                                # 直接写入文件，不使用临时文件
                                with open(file_path, 'w', encoding='utf-8') as tf:
                                    json.dump(json_data, tf, ensure_ascii=False, indent=2)
                                logger.info(f"已将文件 {file_path} 从 {encoding} 编码转换为 UTF-8 编码")
                            except Exception as e:
                                logger.error(f"转换文件编码时出错: {str(e)}")
                        break
                except UnicodeDecodeError:
                    logger.warning(f"使用 {encoding} 编码读取文件 {file_path} 失败，尝试其他编码")
                    continue
                except json.JSONDecodeError:
                    logger.warning(f"文件 {file_path} JSON格式错误")
                    break
                except Exception as e:
                    logger.error(f"读取文件 {file_path} 时出错: {str(e)}")
                    break

            # 如果文件无法读取，创建备份并删除
            if not file_valid:
                # 创建备份
                backup_path = f"{file_path}.corrupted.{int(time.time())}"
                shutil.copy2(file_path, backup_path)

                # 删除原文件
                os.remove(file_path)

                # 创建空文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False)

                logger.info(f"清理了损坏的文件 {file_path}，备份为 {backup_path}")
        except Exception as e:
            logger.error(f"处理文件 {file_path} 时出错: {str(e)}")

    logger.info("清理损坏文件完成")

# 初始获取一次数据
if __name__ == "__main__":
    # 先清理损坏文件
    clean_corrupted_news_files()
    # 然后获取新闻
    fetch_news_task()
