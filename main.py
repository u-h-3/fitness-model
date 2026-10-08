from agent循环 import run_agent
print("智能助手已启动。输入 exit / quit / q 退出。")
messages=[{"role":"system","content":"你是一个智能健身助手，能记录用户性别年龄 身高体重 计算拥有完整信息的用户的tdee 查询食物的可能营养数据 如果用户能详细说吃了什么 还能算出这餐的热量 并记录下来 记录用户的训练部位重量组数次数 。"}]
while True:
    user_input = input("\n用户: ").strip()
    if user_input.lower() in ("exit", "quit", "q"):
        print("再见！")
        break
    if not user_input:               
        continue
    messages.append({"role": "user", "content": user_input})
    answer=run_agent(messages)
    print("助手:", answer)
    