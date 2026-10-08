from openai import OpenAI
import os,json
from tools import TOOLS,FUNC_MAP
client=OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
    )
MAX_STEPS=10

def _call_tool(tc)->str:
    """执行单个工具调用，任何失败都转成字符串返回，绝不抛出"""
    name=tc.function.name
    try:
        args=json.loads(tc.function.arguments or"{}")
    except json.JSONDecodeError as e:
        return f"参数不是合法JSON,请重新生成{e}"
    if not isinstance(args,dict):
        return "参数必须是JSON对象"
    func=FUNC_MAP.get(name)
    if func is None:
        return f"没有名为{name}的工具，可用工具:{','.join(FUNC_MAP)}"
    try:
        return str(func(**args))
    except TypeError as e:
        return f"参数不匹配 请检查参数名和类型:{e}"
    except Exception as e:
        return f"工具执行出错:{type(e).__name__}:{e}"




def run_agent(messages:list)->str:
    for _ in range(MAX_STEPS):
        try:
            response=client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                tools=TOOLS,
            )
        except Exception as e:
            return f"调用模型失败：{e}"
        msg=response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            return msg.content
        for tc in msg.tool_calls:
            result=_call_tool(tc)
            print("调用工具:",tc.function.name,"结果:",result)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content":result})
    return "达到最大步数，仍未结束"
   
