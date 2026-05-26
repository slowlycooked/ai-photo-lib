from __future__ import annotations

ANIMAL_TERMS_TIERED = {
    "猫": {
        "expanded": ["小猫", "猫咪"],
        "broad": ["宠物", "动物"],
        "negative": ["狗", "小狗", "狗狗", "兔子"],
        "facets": ["object"],
    },
    "狗": {
        "expanded": ["小狗", "狗狗"],
        "broad": ["宠物", "动物"],
        "negative": ["猫", "小猫", "猫咪"],
        "facets": ["object"],
    },
    "鸟": {
        "expanded": ["小鸟", "飞鸟", "禽鸟"],
        "broad": ["动物"],
        "facets": ["object"],
    },
    "动物": {
        "expanded": ["猫", "狗", "鸟", "马", "鹿", "兔子", "鱼"],
        "broad": ["宠物", "野生动物", "动物园"],
        "facets": ["object"],
    },
    "猫狗": {
        "expanded": ["猫", "狗"],
        "broad": ["宠物", "动物"],
        "facets": ["object"],
    },
    "宠物": {
        "expanded": ["猫", "狗", "兔子"],
        "broad": ["动物"],
        "facets": ["object"],
    },
    "小动物": {
        "expanded": ["猫", "狗", "兔子", "鸟"],
        "broad": ["宠物", "动物"],
        "facets": ["object"],
    },
    "野生动物": {
        "expanded": ["动物", "野外"],
        "broad": ["自然", "户外"],
        "facets": ["object", "scene"],
    },
    "动物园": {
        "expanded": ["动物", "野生动物"],
        "broad": [],
        "facets": ["scene", "object"],
    },
    "马": {
        "expanded": ["骏马", "骑马"],
        "broad": ["动物"],
        "facets": ["object"],
    },
    "鹿": {
        "expanded": ["梅花鹿", "野鹿"],
        "broad": ["动物"],
        "facets": ["object"],
    },
    "兔子": {
        "expanded": ["小兔"],
        "broad": ["宠物", "动物"],
        "negative": ["猫", "狗"],
        "facets": ["object"],
    },
    "鱼": {
        "expanded": ["水族"],
        "broad": ["海洋", "动物"],
        "facets": ["object"],
    },
    "蝴蝶": {
        "expanded": ["昆虫"],
        "broad": ["花园", "动物"],
        "facets": ["object"],
    },
    "animal": {
        "expanded": ["动物", "猫", "狗", "鸟"],
        "broad": ["宠物", "野生动物"],
        "facets": ["object"],
    },
    "cat": {
        "expanded": ["猫", "小猫"],
        "broad": ["宠物", "动物"],
        "negative": ["狗", "dog"],
        "facets": ["object"],
    },
    "dog": {
        "expanded": ["狗", "小狗"],
        "broad": ["宠物", "动物"],
        "negative": ["猫", "cat"],
        "facets": ["object"],
    },
    "bird": {
        "expanded": ["鸟", "小鸟", "飞鸟"],
        "broad": ["动物"],
        "facets": ["object"],
    },
}
