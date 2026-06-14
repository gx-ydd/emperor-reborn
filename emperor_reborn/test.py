import asyncio

async def fetch_data():
    # 模拟异步请求
    await asyncio.sleep(2)  # 无阻塞等待 2 秒
    return "返回的数据"

async def main():
    # 等待 fetch_data 完成工作，并获取返回值
    data = await fetch_data()
    print(data)  # 输出: 返回的数据

asyncio.run(main()) # 运行协程