from __future__ import annotations

WEATHER_TERMS_TIERED = {
    # Rain group — core evidence: 下雨/雨天/雨滴/雨中
    #              context clues: 雨伞/雨衣/积水/湿地面/淋湿 (support)
    #              weak context:  阴天/多云/潮湿 (broad)
    #              negative:      晴天/阳光/干燥/沙地
    "下雨": {
        "expanded": ["雨天", "雨滴", "雨中"],
        "support": ["雨伞", "雨衣", "积水", "湿地面", "淋湿"],
        "broad": ["阴天", "多云", "潮湿"],
        "negative": ["晴天", "阳光", "干燥", "沙地"],
        "facets": ["weather"],
    },
    "下雨天": {
        "expanded": ["下雨", "雨天", "雨滴", "雨中"],
        "support": ["雨伞", "雨衣", "积水", "湿地面", "淋湿"],
        "broad": ["阴天", "多云", "灰蒙蒙", "潮湿"],
        "negative": ["晴天", "阳光", "沙地", "干燥"],
        "facets": ["weather"],
    },
    "雨天": {
        "expanded": ["下雨", "雨滴", "雨中"],
        "support": ["雨伞", "雨衣", "积水", "湿地面", "淋湿"],
        "broad": ["阴天", "多云", "潮湿"],
        "negative": ["晴天", "阳光"],
        "facets": ["weather"],
    },
    "下雪": {
        "expanded": ["雪天", "雪地", "雪花", "积雪"],
        "broad": ["寒冷", "冬天"],
        "negative": ["晴天", "阳光", "海边", "夏天"],
        "facets": ["weather"],
    },
    "雪天": {
        "expanded": ["下雪", "雪地", "积雪", "雪花"],
        "broad": ["寒冷", "冬天"],
        "negative": ["晴天", "阳光", "海边", "夏天"],
        "facets": ["weather"],
    },
    "晴天": {
        "expanded": ["阳光", "蓝天", "白云"],
        "broad": ["户外"],
        "negative": ["阴天", "多云", "雨天", "雨伞", "积水"],
        "facets": ["weather", "lighting"],
    },
    "出太阳": {
        "expanded": ["晴天", "阳光", "蓝天"],
        "broad": ["白云", "户外", "日照"],
        "negative": ["阴天", "多云", "雨天"],
        "facets": ["weather", "lighting"],
    },
    "太阳": {
        "expanded": ["晴天", "阳光", "蓝天"],
        "broad": ["白云", "户外", "日照"],
        "negative": ["阴天", "多云"],
        "facets": ["lighting"],
    },
    "阳光": {
        "expanded": ["晴天", "蓝天", "白云"],
        "broad": ["户外", "日照"],
        "negative": ["阴天", "多云", "夜晚", "夜色"],
        "facets": ["lighting", "weather"],
    },
    "晴朗": {
        "expanded": ["晴天", "阳光", "蓝天"],
        "broad": ["白云", "户外"],
        "negative": ["阴天", "多云"],
        "facets": ["weather"],
    },
    "阴天": {
        "expanded": ["多云", "乌云"],
        "broad": ["灰色天空", "灰蒙蒙"],
        "negative": ["晴天", "阳光", "蓝天"],
        "facets": ["weather"],
    },
    "大风": {
        "expanded": ["风大", "风吹"],
        "broad": ["户外", "飞扬"],
        "facets": ["weather"],
    },
    "雨伞": {
        "expanded": ["下雨", "雨天"],
        "broad": ["防雨"],
        "facets": ["weather", "object"],
    },
    "rain": {
        "expanded": ["下雨", "雨天", "雨滴", "雨中"],
        "support": ["雨伞", "雨衣", "积水", "湿地面", "淋湿"],
        "broad": ["阴天", "多云", "潮湿", "灰蒙蒙"],
        "negative": ["晴天", "阳光", "沙地"],
        "facets": ["weather"],
    },
    "snow": {
        "expanded": ["下雪", "雪天", "雪地", "积雪", "雪花"],
        "broad": ["寒冷", "冬天"],
        "negative": ["晴天", "阳光", "海边", "夏天"],
        "facets": ["weather"],
    },
    "sunny": {
        "expanded": ["晴天", "阳光", "蓝天", "白云"],
        "broad": ["户外"],
        "negative": ["阴天", "多云", "雨天"],
        "facets": ["weather", "lighting"],
    },
    "sunshine": {
        "expanded": ["阳光", "晴天", "蓝天", "白云"],
        "broad": ["户外"],
        "negative": ["阴天", "多云"],
        "facets": ["lighting", "weather"],
    },
}
