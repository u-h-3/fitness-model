import os,sqlite3,requests,datetime
DB_PATH=os.path.join(os.path.dirname(os.path.abspath(__file__)),"test.db")
ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}
FOOD_BASE_URL="https://api.nal.usda.gov/fdc/v1/foods/search"
FOOD_API_KEY=os.getenv("USDA_API_KEY","DEMO_KEY")
def search_food(food_name:str)->str:
    params={
        "api_key":FOOD_API_KEY,
        "query":food_name,
        "dataType":"SR Legacy",
        "pageSize":5,
        "requireAllWords":"true"
    }
    resp= requests.get(FOOD_BASE_URL,params=params,timeout=10)
    if resp.status_code!=200:
        return f"请求失败,状态码{resp.status_code},可能是key无效或网络问题"
    data=resp.json()
    foods=data.get("foods")
    if not foods:
        return f"没查到{food_name}的营养数据，换个英文名试试"
    lines=[f"{food_name}有{len(foods)}个可能结果,请记下要选的fdcId:"]
    for i,food in enumerate(foods,1):
        raw={}
        for n in food.get("foodNutrients",[]):
            k=n.get("nutrientName")
            if k is None:
                continue
            raw[k]=_norm_value(k,n.get("unitName"),n.get("value"))
        desc=food.get("description",food_name)
        kcal=raw.get("Energy")
        protein=raw.get("Protein")
        fat=raw.get("Total lipid (fat)")
        carb=raw.get("Carbohydrate, by difference")
        lines.append(f"{i}.fdcId={food.get('fdcId')} {desc} |每100克 热量{kcal}kcal 蛋白质{protein}g 脂肪{fat}g 碳水化合物{carb}g")
    return"\n".join(lines)
   
def _norm_value(name,unit,amount):
    """把 Energy 统一成 kcal；其他营养素原样返回"""
    if amount is None:
        return None
    if name=="Energy" and unit=="kJ":
        return amount/4.184
    return amount


def _food_by_id(fdc_id:int)->dict|None:
    """按 fdcId 精确取一个食物的营养 dict(Energy 统一为 kcal);查不到返回 None"""
    url = f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}"
    params={   
        "api_key":FOOD_API_KEY,
        "format":"abridged"
    }  
    resp=requests.get(url,params=params,timeout=10)
    if resp.status_code!=200:
        return None
    data=resp.json()
    out={}
    for n in data.get("foodNutrients",[]):
        name=n.get("name")
        if name is None:
            continue
        out[name]=_norm_value(name,n.get("unitName"),n.get("amount"))
    return out
  
def _ensure_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS gym(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            height REAL NOT NULL,
            weight REAL NOT NULL
        )
        '''
    )
    conn.commit()
    conn.close()

def _food_table():
    conn=sqlite3.connect(DB_PATH)
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS food(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            meal_type TEXT NOT NULL,
            date TEXT NOT NULL,
            food_name TEXT NOT NULL,
            weight REAL NOT NULL
        )
        '''
    )
    conn.commit()
    conn.close()

def _work_out():
    conn=sqlite3.connect(DB_PATH)
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS workout(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            body_part TEXT NOT NULL,
            date TEXT NOT NULL,
            action_name TEXT NOT NULL,
            action_weight REAL NOT NULL,
            action_sets INTEGER NOT NULL,
            action_reps INTEGER NOT NULL

        )
        '''
    )
    conn.commit()
    conn.close()

def log_work_out(name:str,body_part:str,action_name:str,action_weight:float,action_sets:int,action_reps:int,date:str=None)->str:
    if date is None:
        date=datetime.date.today().isoformat()
    _work_out()
    conn=sqlite3.connect(DB_PATH)
    cursor=conn.cursor()
    cursor.execute(
        "INSERT INTO workout(name,body_part,date,action_name,action_weight,action_sets,action_reps)VALUES(?,?,?,?,?,?,?)",
        (name,body_part,date,action_name,action_weight,action_sets,action_reps)
    )
    conn.commit()
    conn.close()
    return f"{name} {date} {body_part} {action_name} {action_weight}kg {action_sets}组 {action_reps}次 已记录"

def log_meal(name,foods,meal_type="加餐",date=None)->str:
    if meal_type not in ("早餐","午餐","晚餐","加餐"):
        return "meal_type 只能是 早餐/午餐/晚餐/加餐"
    if date is None:
        date=datetime.date.today().isoformat()
    _food_table()
    totals={"Energy":0.0,"Protein":0.0,"Total lipid (fat)":0.0,"Carbohydrate, by difference":0.0}
    lines=[f"{name} {meal_type} {date}:"]
    saved=[]
    for item in foods:
        food_name=item.get("food_name")
        weight=item.get("weight")
        if not food_name or weight is None:
            lines.append("（有一条食物记录缺 food_name 或 weight，已跳过）")
            continue
        fdc_id=item.get("fdcId")
        if fdc_id is None:
            lines.append(f"{food_name} {weight}克（缺 fdcId，未记录）")
            continue
        nut=_food_by_id(fdc_id)
        if nut is None or nut.get("Energy") is None:
            lines.append(f"{food_name} {weight}克（未查到营养数据，未记录）")
            continue
        kcal=nut["Energy"]*weight/100
        totals["Energy"]+=kcal
        for key in ("Protein","Total lipid (fat)","Carbohydrate, by difference"):
            v=nut.get(key)
            if v is not None:
                totals[key]+=v*weight/100
        saved.append((name,meal_type,date,food_name,weight))
        lines.append(f"{food_name}{weight}克≈ {kcal:.0f} kcal")
    if saved:
        conn=sqlite3.connect(DB_PATH)
        try:
            conn.executemany(
                "INSERT INTO food(name,meal_type,date,food_name,weight)VALUES(?,?,?,?,?)",
                saved,
            )
            conn.commit()
        finally:
            conn.close()
    lines.append(
    f"合计：Energy {totals['Energy']:.0f} kcal, "
    f"Protein {totals['Protein']:.1f} g, "
    f"Fat {totals['Total lipid (fat)']:.1f} g, "
    f"Carb {totals['Carbohydrate, by difference']:.1f} g"
)
    return "\n".join(lines)
        
def query_food_table(name:str,date:str=None)->str:
    if date is None:
        date=datetime.date.today().isoformat()
    _food_table()
    conn=sqlite3.connect(DB_PATH)
    try:
        cursor=conn.cursor()
        cursor.execute("SELECT * FROM food WHERE name=? AND date=?",(name,date))
        rows=cursor.fetchall()
    finally:
        conn.close()
    if not rows:
        return f"{name}在表里没有记录任何食物"
    lines=[f"{name} {date} 饮食记录："]
    for row in rows:
        _id,_name,_meal_type,_date,_food_name,_weight=row
        lines.append(
            f"{_name} {_date} "
            f"{_meal_type} {_food_name} {_weight}克")
    return "\n".join(lines)

def query_work_out(name:str,date:str=None)->str:
    if date is None:
        date=datetime.date.today().isoformat()
    _work_out()
    conn=sqlite3.connect(DB_PATH)
    try:
        cursor=conn.cursor()
        cursor.execute("SELECT * FROM workout WHERE name=? AND date=?",(name,date))
        rows=cursor.fetchall()
    finally:
        conn.close()
    if not rows:
        return f"{name}在表里没有训练记录"
    lines=[f"{name} {date}的训练记录:"]
    for row in rows:
        _id,_name,_body_part,_date,_action_name,_action_weight,_action_sets,_action_reps=row
        lines.append(
            f"{_name} {_date} "
            f"部位:{_body_part} 动作:{_action_name} "
            f"{_action_weight}kg {_action_sets}组×{_action_reps}次"
        )
    return "\n".join(lines)

def update_user_profile(name:str, gender:str, age:int, height:float, weight:float)->str:
    if gender not in ("男", "女"):
        return "性别只能是'男'或'女'"
    _ensure_table()
    conn=sqlite3.connect(DB_PATH)
    cursor=conn.cursor()
    cursor.execute("SELECT id FROM gym WHERE name=?",(name,))
    exists=cursor.fetchone()
    if exists:
        cursor.execute(
            "UPDATE gym SET age=?,gender=?,height=?,weight=? WHERE name=?",(age,gender,height,weight,name),
        )
        conn.commit()
        cursor.execute("SELECT * FROM gym WHERE name=?", (name,))
        row = cursor.fetchone()
        conn.close()

        _id, _name, _age, _gender, _height, _weight = row
        return (
            "更新成功，新用户数据为："
            f"姓名：{_name},"
            f"年龄：{_age},"
            f"性别：{_gender},"
            f"身高：{_height},"
            f"体重：{_weight}"
        )
    else:
        cursor.execute("INSERT INTO gym(name,gender,age,height,weight)VALUES(?,?,?,?,?)",(name,gender,age,height,weight))
        conn.commit()
        new_id=cursor.lastrowid
        cursor.execute("SELECT * FROM gym WHERE id = ?", (new_id,))
        row= cursor.fetchone()
        conn.close()
        _id,_name,_age,_gender,_height,_weight=row
        return(
        f"姓名：{_name},"
        f"年龄:{_age},"
        f"性别:{_gender},"
        f"身高：{_height},"
        f"体重:{_weight}"
        )


def calculate_BMR(name:str)->float|None:
    ios=get_user(name)
    if ios is None:
        return None
    if ios['gender']=="男":
        results=10*ios['weight']+6.25*ios['height']-5*ios['age']+5
        return results
    if ios['gender']=="女":
        results=10*ios['weight']+6.25*ios['height']-5*ios['age']-161
        return results
    raise ValueError("性别信息无效 应为'男'或'女'")

def calculate_tdee(name:str,activity_level:str)->str:
    try:
        BMR=calculate_BMR(name)
    except ValueError as e:
        return str(e)
    if BMR is None:
        return "未存入该用户的具体信息 请完善"
    if activity_level not in ACTIVITY_FACTORS:
        return "activity_level 必须是 sedentary/light/moderate/active/very_active"
    factor=ACTIVITY_FACTORS[activity_level]
    tdee=factor*BMR
    return (
        f"BMR≈{BMR:.0f} kcal，"
        f"活动等级={activity_level}，"
        f"活动系数={factor}，"
        f"TDEE≈{tdee:.0f} kcal/天"
    )

    


def calculate(a:float,b:float,operator:str)->str:
    """做一个简单的四则运算"""
    if operator =="+":
        result=a+b
    elif operator =="-":
        result=a-b
    elif operator =="*":
        result=a*b
    elif operator =="/":
        if b==0:
            return "除数不能为零"
        result=a/b
    else:
        return "不支持的运算符"
    return f"{a} {operator} {b} = {result}"

def query_users()->list[dict]|str:
    _ensure_table()
    conn=sqlite3.connect(DB_PATH)
    cursor=conn.cursor()
    cursor.execute("SELECT * FROM gym")
    rows=cursor.fetchall()
    conn.close()
    if not rows:
        return "没有用户数据"
    else:
        return [{"id":r[0],"name":r[1],"age":r[2],"gender":r[3],"height":r[4],"weight":r[5]}for r in rows]

def query_name(name:str)->str:
    pop=get_user(name)
    if pop is None:
        return "查不到该用户"
    return (
        f"姓名：{pop['name']},"
        f"年龄:{pop['age']},"
        f"性别:{pop['gender']},"
        f"身高：{pop['height']},"
        f"体重:{pop['weight']}"
    )
def get_user(name:str)->dict|None:
    _ensure_table()
    conn=sqlite3.connect(DB_PATH)
    cursor=conn.cursor()
    cursor.execute("SELECT * FROM gym WHERE name=?",(name,))
    row=cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "age": row[2],
        "gender": row[3],
        "height": row[4],
        "weight": row[5],
    }



TOOLS=[
    {
        "type":"function",
        "function":{
            "name":"log_meal",
            "description":"记录用户某一餐吃了什么、各吃了多少克，并自动算出总热量和营养素 最后告诉用户他是以什么日期存储的",
            "parameters":{
                "type":"object",
                "properties":{
                    "name":{
                        "type":"string",
                        "description":"用户姓名 必填"
                    },
                    "meal_type":{
                        "type":"string",
                        "enum":["早餐","午餐","晚餐","加餐"],
                        "description":"哪一餐"
                    },
                    "foods": {
                        "type": "array",
                        "description": "每个食物必须先调用 search_food，把选中候选的 fdcId 填进来",
                        "items": {
                            "type": "object",
                            "properties": {
                                "food_name": {"type": "string", "description": "食物名（用于显示，可用中文）"},
                                "fdcId": {"type": "integer", "description": "search_food 返回的选中食物的 fdcId，必填"},
                                "weight": {"type": "number", "description": "吃的克数"}

                            },
                            "required": ["name","food_name", "fdcId", "weight"]
                        }
                    },
                    "date": {
                        "type": "string",
                        "description": "用餐日期，格式 YYYY-MM-DD"
                    },

                },
                "required":["name","foods"]
            },
        },
    },
    {
    "type": "function",
    "function": {
        "name": "search_food",
        "description": (
            "查询某食物每100克的热量、蛋白质、脂肪、碳水化合物等基础营养素。"
            "注意：food_name 必须用英文调用，先把用户说的中文食物名翻译成英文"
            "（如 鸡蛋→egg、米饭→rice、鸡胸肉→chicken breast），再传给函数。"
            "分析获取的值 来判断是否再次调用search_food，直到找到合适的 fdcId。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "food_name": {
                    "type": "string",
                    "description": "食物的英文名称，例如 egg、rice、chicken breast"
                }
            },
            "required": ["food_name"],
        },
    },
},

    {
    "type":"function",
    "function":{
        "name":"query_food_table",
        "description":"查询某用户在某天的食物记录 返回姓名 全天的餐次 食物 重量",
        "parameters":{
            "type":"object",
            "properties":{
                "name":{
                    "type":"string",
                    "description":"用户姓名 必填"
                },
                "date":{
                    "type":"string",
                    "description":"查询日期"
                }
            },
            "required":["name","date"],
        },
    },
},


    {
    "type":"function",
    "function":{
        "name":"query_work_out",
        "description":"查询某用户在某天的训练记录 返回姓名 身体部位 日期 动作名称 动作重量 动作组数 动作次数",
        "parameters":{
            "type":"object",
            "properties":{
                "name":{
                    "type":"string",
                    "description":"用户姓名 必填"
                },
                "date":{
                    "type":"string",
                    "description":"查询日期，格式 YYYY-MM-DD，不填默认今天"
                }
            },
            "required":["name","date"],
        },
    },
},
    {
        "type":"function",
        "function":{
            "name":"calculate_tdee",
            "description": (
            "计算每日总能量消耗 TDEE。"
            "你必须根据用户描述选择 activity_level，不能自己编活动系数。"
            "activity_level 只能从五个枚举中选。"
        ),
        "parameters":{
            "type":"object",
            "properties":{"name":{"type":"string","description":"用户姓名"},
            "activity_level": {
                    "type": "string",
                    "enum": [
                        "sedentary",
                        "light",
                        "moderate",
                        "active",
                        "very_active"
                    ],
                    "description": (
                        "sedentary=久坐/几乎不运动/步数<5000；"
                        "light=每周1-3次轻运动/偶尔散步；"
                        "moderate=每周3-5次中等运动；"
                        "active=每周6-7次或每天训练；"
                        "very_active=体力劳动+每天高强度/运动员。"
                        "模糊时选更低一级或先追问。"
                    )
                }},
            "required":["name","activity_level"],
        },
        },
    },
    {
        "type":"function",
        "function":{
            "name":"query_name",
            "description":"通过姓名去查询某个用户的信息 名字必填",
            "parameters":{
                "type":"object",
                "properties":{"name":{"type":"string","description":"用户姓名 必填"}},
                "required":["name"],
            },
        },
    },
    {
        "type":"function",
        "function":{
            "name":"update_user_profile",
            "description":"存储或更新用户的姓名 年龄 性别身高 体重到库里面 name是姓名 age是年龄gender是性别 height是身高 weight是体重 ",
            "parameters":{
                "type":"object",
                "properties": {
            "name": {
            "type": "string",
            "description": "用户名称，例如：张三 必须填"
            },
            "gender": {
            "type": "string",
            "enum":["男","女"],
            "description": "用户性别，例如：男 必须填 只能以男 女这两个形式存"
            },
            "height": {
            "type": "number",
            "description": "身高，单位 cm，例如：175.5 必须填"
            },
            "age": {
            "type": "integer",
            "description": "年龄，例如：30 必须填"
            },
            "weight": {
            "type": "number",
            "description": "体重，单位 kg，例如：70.5 必须填"
            },

            
            },
            "required":["name","age","gender","height","weight"],
        },
    },
    },
    {
        "type":"function",
        "function":{
            "name":"calculate",
            "description":"当用户需要做四则运算时调用，参数 a、b 是数字，operator 是 + - * / 之一",
            "parameters":{
                "type":"object",
                "properties":{"a":{"type":"number","description":"第一个数字"},"b":{"type":"number","description":"第二个数字"},"operator":{"type":"string","description":"运算符，支持 + - * /"}},
                "required":["a","b","operator"],
            },
        },
    },
    {
        "type":"function",
        "function":{
            "name":"query_users",
            "description":"当用户需要查询所有用户信息时调用，无需参数",
            "parameters":{
                "type":"object",
                "properties":{},
                "required":[],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_work_out",
            "description": "记录某用户的一次力量训练 返回姓名 日期 部位 动作 重量 组数 次数",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                    "type": "string",
                    "description": "用户姓名 必填"
                    },
                    "body_part": {
                    "type": "string",
                    "description": "训练部位 如 胸 背 腿 肩 必填"
                    },
                    "action_name": {
                    "type": "string",
                    "description": "动作名称 如 卧推 深蹲 必填"
                    },
                    "action_weight": {
                    "type": "number",
                    "description": "动作重量 单位 kg 必填"
                    },
                    "action_sets": {
                    "type": "integer",
                    "description": "动作组数 必填"
                    },
                    "action_reps": {
                    "type": "integer",
                    "description": "每组次数 必填"
                    },
                    "date": {
                    "type": "string",
                    "description": "训练日期，格式 YYYY-MM-DD，不填默认今天"
                    }
                },
            "required": ["name", "body_part", "action_name", "action_weight", "action_sets", "action_reps"]
        },
    },
},


]

FUNC_MAP={
    "calculate": calculate,
    "query_users": query_users,
    "update_user_profile":update_user_profile,
    "query_name":query_name,
    "calculate_tdee":calculate_tdee,
    "search_food":search_food,
    "log_meal":log_meal,
    "query_food_table":query_food_table,
    "log_work_out":log_work_out,
    "query_work_out":query_work_out
}
