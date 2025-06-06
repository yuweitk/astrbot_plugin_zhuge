from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import sqlite3
from datetime import datetime, timedelta
import os
from typing import Dict, Tuple
import asyncio
import logging

@register(
    "zhuge_shensuan",
    "诸葛神算插件",
    "诸葛神算每日求签解签",
    "1.0.0",
    "https://github.com/yuweitk/astrbot_plugin_zhuge"
)
class ZhugePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(plugin_dir, 'zhuge.db')
        self.user_records: Dict[str, Tuple[datetime, int]] = {}
        
        # 正确初始化日志记录器 [4,7](@ref)
        self.logger = logging.getLogger(__name__)
        
        # 初始化数据库连接
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        
        # 创建每日清理任务
        self.cleanup_task = asyncio.create_task(self._daily_cleanup_task())

    async def _daily_cleanup_task(self):
        """每天凌晨清理用户记录"""
        try:
            while True:
                now = self._get_beijing_time()
                # 计算到下一天凌晨的时间
                next_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                wait_seconds = (next_day - now).total_seconds()
                
                # 等待到第二天的凌晨
                await asyncio.sleep(wait_seconds)
                self.user_records.clear()
                self.logger.info("每日用户记录已清零")
        except asyncio.CancelledError:
            self.logger.info("清理任务已取消")
        except Exception as e:
            self.logger.error(f"清理任务异常: {str(e)}")

    def _get_beijing_time(self) -> datetime:
        """获取北京时间的当前时间"""
        return datetime.utcnow() + timedelta(hours=8)

    def _check_quota(self, user_id: str) -> bool:
        """检查用户当日求签次数是否超限"""
        current_date = self._get_beijing_time().date()
        
        if user_id in self.user_records:
            last_time, count = self.user_records[user_id]
            if last_time.date() == current_date:
                return count < 3
        return True

    def _update_quota(self, user_id: str):
        """更新用户求签次数记录"""
        now = self._get_beijing_time()
        
        if user_id in self.user_records:
            last_time, count = self.user_records[user_id]
            if last_time.date() == now.date():
                self.user_records[user_id] = (now, count + 1)
            else:
                self.user_records[user_id] = (now, 1)
        else:
            self.user_records[user_id] = (now, 1)

    @filter.command("诸葛神算")
    async def zhuge_shensuan(self, event: AstrMessageEvent):
        """诸葛神算每日求签功能"""
        user_id = event.get_sender_id()
        
        # 检查每日次数限制
        if not self._check_quota(user_id):
            yield event.plain_result("❌ 今日求签次数已用尽，请明日再来")
            return
        
        try:
            # 随机获取一条签文
            self.cursor.execute("SELECT text FROM zhuge ORDER BY RANDOM() LIMIT 1")
            result = self.cursor.fetchone()
            
            if not result:
                yield event.plain_result("⚠️ 签文数据库为空，请联系管理员")
                return
                
            self._update_quota(user_id)
            used_count = self.user_records[user_id][1]
            
            # 格式化签文结果
            msg = (
                "🔮 诸葛神算 | 今日签文\n"
                "------------------------\n"
                f"{result[0]}\n"
                "------------------------\n"
                f"🎫 今日剩余次数: {3 - used_count}/3"
            )
            yield event.plain_result(msg)
            
        except sqlite3.Error as e:
            yield event.plain_result("⚠️ 签筒暂时无法使用，请稍后再试")
            self.logger.error(f"数据库错误: {str(e)}")
            
        except Exception as e:
            yield event.plain_result("⚠️ 系统异常，请联系管理员")
            self.logger.error(f"未知错误: {str(e)}")

    async def terminate(self):
        """插件终止时执行清理操作"""
        # 取消定时清理任务
        self.cleanup_task.cancel()
        try:
            await self.cleanup_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"任务取消异常: {str(e)}")
        
        # 关闭数据库连接
        try:
            self.cursor.close()
            self.conn.close()
            self.logger.info("诸葛神算插件已安全关闭")
        except Exception as e:
            self.logger.error(f"数据库关闭异常: {str(e)}")