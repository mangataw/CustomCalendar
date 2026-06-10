import os
import datetime
import yaml
from icalendar import Calendar, Event
import chinese_calendar as calendar
from lunar_python import Lunar, Solar
from astral import moon

# 假期中文翻译映射
HOLIDAY_CN = {
    "New Year's Day": "元旦",
    "Spring Festival": "春节",
    "Tomb-sweeping Day": "清明节",
    "Labour Day": "劳动节",
    "Dragon Boat Festival": "端午节",
    "National Day": "国庆节",
    "Mid-autumn Festival": "中秋节",
    "Anti-Fascist 70th Day": "抗战胜利纪念日"
}

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if not os.path.exists(config_path):
        return {
            "calendar_range": {"years_backward": 1, "years_forward": 2},
            "anniversaries": []
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def init_calendar(name):
    cal = Calendar()
    cal.add('prodid', '-//Kaze//Calendar Generator//CN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', name)
    cal.add('x-wr-timezone', 'Asia/Shanghai')
    return cal

def create_event(summary, date_obj, event_type):
    event = Event()
    event.add('summary', summary)
    event.add('dtstart', date_obj)
    event.add('dtend', date_obj + datetime.timedelta(days=1))
    
    # 稳定唯一的 UID，避免在客户端导入/同步时产生重复事件
    uid = f"{date_obj.strftime('%Y%m%d')}-{event_type}@kaze.calendar.github"
    event.add('uid', uid)
    
    # 标记为透明（FREE），不占用用户日历的 busy 忙碌状态
    event.add('transp', 'TRANSPARENT')
    return event

def precompute_holidays(start_year, end_year):
    """
    预计算每年每种放假/调休的日期列表，用于计算“第X天/共Y天”的排班天数
    返回结构: holiday_groups[year][(is_holiday, holiday_name)] = [date1, date2, ...]
    """
    holiday_groups = {}
    for y in range(start_year, end_year + 1):
        holiday_groups[y] = {}
        # 遍历全年的每一天
        start_date = datetime.date(y, 1, 1)
        for i in range(366):
            d = start_date + datetime.timedelta(days=i)
            if d.year != y:
                break
            
            try:
                is_hol = calendar.is_holiday(d)
                is_wk = calendar.is_workday(d)
                on_h, h_name = calendar.get_holiday_detail(d)
            except NotImplementedError:
                # 针对尚未公布放假安排的未来年份，回退到普通周末双休逻辑
                is_hol = d.weekday() >= 5
                is_wk = not is_hol
                on_h, h_name = False, None
            
            if h_name is not None:
                # 判断是放假（is_holiday=True）还是调休上班（is_holiday=False, is_workday=True）
                # 用 (on_h, h_name) 作为键进行分组
                key = (on_h, h_name)
                if key not in holiday_groups[y]:
                    holiday_groups[y][key] = []
                holiday_groups[y][key].append(d)
                
        # 确保列表升序排序
        for key in holiday_groups[y]:
            holiday_groups[y][key].sort()
            
    return holiday_groups

def get_moon_phase_str(date_obj):
    p = moon.phase(date_obj)
    if p < 1.0 or p >= 27.0:
        return "🌑", "新月"
    elif 1.0 <= p < 6.0:
        return "🌒", "娥眉月"
    elif 6.0 <= p < 8.0:
        return "🌓", "上弦月"
    elif 8.0 <= p < 13.0:
        return "🌔", "盈凸月"
    elif 13.0 <= p < 15.0:
        return "🌕", "满月"
    elif 15.0 <= p < 20.0:
        return "🌖", "亏凸月"
    elif 20.0 <= p < 22.0:
        return "🌗", "下弦月"
    else:
        return "🌘", "残月"

def main():
    config = load_config()
    range_cfg = config.get("calendar_range", {})
    years_backward = range_cfg.get("years_backward", 1)
    years_forward = range_cfg.get("years_forward", 2)
    
    current_year = datetime.date.today().year
    start_year = current_year - years_backward
    end_year = current_year + years_forward - 1
    
    print(f"Generating calendar from {start_year}-01-01 to {end_year}-12-31")
    
    start_date = datetime.date(start_year, 1, 1)
    end_date = datetime.date(end_year, 12, 31)
    
    # 预计算放假与调休分组
    holiday_groups = precompute_holidays(start_year, end_year)
    
    # 初始化 11 个日历源
    calendars = {
        "holidays": init_calendar("国定节假日"),
        "workdays": init_calendar("调休上班"),
        "lunar_date": init_calendar("农历日期"),
        "lunar_ganzhi": init_calendar("天干地支"),
        "lunar_jieqi": init_calendar("二十四节气"),
        "lunar_xingxiu": init_calendar("二十八星宿"),
        "lunar_yiji": init_calendar("宜忌吉凶"),
        "lunar_caiwei": init_calendar("财位"),
        "moon_phases": init_calendar("月相"),
        "anniversaries": init_calendar("纪念日"),
        "all_in_one": init_calendar("汇总日历")
    }
    
    # 遍历日期生成事件
    delta = end_date - start_date
    for i in range(delta.days + 1):
        d = start_date + datetime.timedelta(days=i)
        
        # 1. 节假日 & 调休日
        try:
            is_hol = calendar.is_holiday(d)
            is_wk = calendar.is_workday(d)
            on_h, h_name = calendar.get_holiday_detail(d)
        except NotImplementedError:
            # 回退到普通周末双休逻辑
            is_hol = d.weekday() >= 5
            is_wk = not is_hol
            on_h, h_name = False, None
        
        if h_name is not None:
            cn_holiday_name = HOLIDAY_CN.get(h_name, h_name)
            group = holiday_groups[d.year].get((on_h, h_name), [])
            total_days = len(group)
            day_index = group.index(d) + 1 if d in group else 1
            
            if on_h:
                # 属于节假日放假
                title = f"{cn_holiday_name} (第{day_index}天/共{total_days}天)" if total_days > 1 else cn_holiday_name
                ev = create_event(title, d, "holiday")
                calendars["holidays"].add_component(ev)
                calendars["all_in_one"].add_component(ev)
            elif is_wk:
                # 属于调休上班
                title = f"{cn_holiday_name}调休 (第{day_index}天/共{total_days}天)" if total_days > 1 else f"{cn_holiday_name}调休"
                ev = create_event(title, d, "workday")
                calendars["workdays"].add_component(ev)
                calendars["all_in_one"].add_component(ev)
                
        # 加载农历/黄历数据
        lunar = Solar.fromYmd(d.year, d.month, d.day).getLunar()
        
        # 2. 农历日期 (例如: 四月廿五)
        lunar_date_str = f"{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}"
        ev = create_event(lunar_date_str, d, "lunar_date")
        calendars["lunar_date"].add_component(ev)
        calendars["all_in_one"].add_component(ev)
        
        # 3. 天干地支 (例如: 丙午马年 甲午月 乙卯日)
        ganzhi_str = f"{lunar.getYearInGanZhi()}{lunar.getYearShengXiao()}年 {lunar.getMonthInGanZhi()}月 {lunar.getDayInGanZhi()}日"
        ev = create_event(ganzhi_str, d, "lunar_ganzhi")
        calendars["lunar_ganzhi"].add_component(ev)
        calendars["all_in_one"].add_component(ev)
        
        # 4. 二十四节气 (交节气当天显示)
        jieqi = lunar.getJieQi()
        if jieqi:
            ev = create_event(jieqi, d, "lunar_jieqi")
            calendars["lunar_jieqi"].add_component(ev)
            calendars["all_in_one"].add_component(ev)
            
        # 5. 二十八星宿 (例如: 北方玄武.壁水獝)
        xingxiu_str = f"{lunar.getGong()}方{lunar.getShou()}.{lunar.getXiu()}{lunar.getZheng()}{lunar.getAnimal()}"
        ev = create_event(xingxiu_str, d, "lunar_xingxiu")
        calendars["lunar_xingxiu"].add_component(ev)
        calendars["all_in_one"].add_component(ev)
        
        # 6. 宜忌吉凶
        yi_list = lunar.getDayYi()
        ji_list = lunar.getDayJi()
        yiji_str = f"宜: {' '.join(yi_list)} / 忌: {' '.join(ji_list)}"
        ev = create_event(yiji_str, d, "lunar_yiji")
        calendars["lunar_yiji"].add_component(ev)
        calendars["all_in_one"].add_component(ev)
        
        # 7. 财位
        caiwei_str = f"财位: {lunar.getDayPositionCaiDesc()}"
        ev = create_event(caiwei_str, d, "lunar_caiwei")
        calendars["lunar_caiwei"].add_component(ev)
        calendars["all_in_one"].add_component(ev)
        
        # 8. 月相
        emoji, name = get_moon_phase_str(d)
        moon_str = f"{emoji} {name}"
        ev = create_event(moon_str, d, "moon_phase")
        calendars["moon_phases"].add_component(ev)
        calendars["all_in_one"].add_component(ev)
        
        # 9. 纪念日
        anniversaries = config.get("anniversaries", [])
        for anniv in anniversaries:
            anniv_date = anniv.get("date", "")
            anniv_title = anniv.get("title", "")
            start_yr = anniv.get("start_year")
            
            # format date as MM-DD
            if anniv_date == d.strftime("%m-%d"):
                if start_yr is not None:
                    years = d.year - start_yr
                    if years >= 0:
                        title = f"🎂 {anniv_title} (第{years}年)"
                    else:
                        continue
                else:
                    title = f"🎂 {anniv_title}"
                
                # 独立类型命名为 anniversary_ID 来避免 UID 碰撞
                ev_anniv = create_event(title, d, f"anniv_{anniv_title}")
                calendars["anniversaries"].add_component(ev_anniv)
                calendars["all_in_one"].add_component(ev_anniv)
                
    # 创建 dist 输出文件夹并写入文件
    dist_dir = os.path.join(os.path.dirname(__file__), "dist")
    os.makedirs(dist_dir, exist_ok=True)
    
    for key, cal in calendars.items():
        file_path = os.path.join(dist_dir, f"{key}.ics")
        with open(file_path, "wb") as f:
            f.write(cal.to_ical())
        print(f"Successfully generated: {file_path} (Size: {os.path.getsize(file_path)} bytes)")

if __name__ == "__main__":
    main()
