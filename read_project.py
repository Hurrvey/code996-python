import asyncio
import os
from openai import OpenAI
from dotenv import load_dotenv
from contextlib import AsyncExitStack

# 加载.env文件，确保API Key受到保护
load_dotenv()

class MCPClient:
    """
    MCP客户端类，用于与OpenAI API进行交互并处理用户查询。
    属性:
        exit_stack (AsyncExitStack): 异步上下文管理器堆栈，用于资源清理。
        openai_api_key (str): 从环境变量中读取的OpenAI API密钥。
        base_url (str): 从环境变量中读取的基础URL。
        model (str): 从环境变量中读取的模型名称。
        client (OpenAI): OpenAI客户端实例。
    """
    def __init__(self):
        """初始化 MCP 客户端"""
        self.exit_stack = AsyncExitStack()
        self.openai_api_key = os.getenv("ds_api_key") # 读取 OpenAI API Key
        self.base_url = os.getenv("ds_base_url") # 读取 BASE URL
        self.model = os.getenv("ds_model") # 读取 model
        if not self.openai_api_key:
            raise ValueError("未找到 OpenAI API Key，请在 .env 文件中设置 OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.openai_api_key, base_url=self.base_url)

    async def process_query(self, query: str) -> str:
        """
        调用 OpenAI API 处理用户查询（异步包装版）
        参数:
            query (str): 用户输入的问题或指令。
        返回:
            str: 来自OpenAI API的回答内容；如果出现异常则返回错误信息。
        """
        messages = [
            {"role": "system", "content": "你是一个智能助手，帮助用户回答问题。"},
            {"role": "user", "content": query}
        ]
        try:
            # 使用run_in_executor在单独线程中运行同步API调用
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._sync_call_api(messages)
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"! 调用 OpenAI API 时出错：{str(e)}"

    def _sync_call_api(self, messages):
        """
        同步方式调用OpenAI Chat Completion接口
        参数:
            messages (list): 包含对话历史的消息列表。
        返回:
            对象: OpenAI API响应对象。
        """
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )

    async def chat_loop(self):
        """
        运行一个交互式的聊天循环，持续接收用户输入并输出AI回复，
        直到用户输入'quit'为止。
        """
        print("\n# MCP客户端已启动！输入'quit'退出")
        while True:
            try:
                query = input("\n你：").strip()
                if query.lower() == 'quit':
                    break
                response = await self.process_query(query)  # 正确传递query参数
                print(f"\nOpenAI: {response}")
            except Exception as e:
                print(f"\n!发生错误：{str(e)}")

    async def cleanup(self):
        """
        清理所有通过exit_stack注册的异步资源。
        """
        await self.exit_stack.aclose()

async def main():
    """
    主函数，创建MCPClient实例，并启动聊天循环。
    在程序结束前执行必要的清理操作。
    """
    client = MCPClient()
    try:
        await client.chat_loop()
    finally:
        if hasattr(client, 'cleanup'):
            await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())