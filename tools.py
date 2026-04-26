from langchain_core.tools import tool

from logger import get_logger

logger = get_logger("tools")


@tool
def get_weather(city: str) -> str:
    """查询指定城市的当前天气。参数 city 为城市名，如：北京、上海。"""
    logger.info(f"调用 get_weather 工具，参数 city={city}")
    try:
        return f"{city}：晴，25℃，微风。"
    except Exception:
        logger.exception(f"get_weather 工具执行失败, city={city}")
        return f"抱歉，查询 {city} 天气时出错。"
