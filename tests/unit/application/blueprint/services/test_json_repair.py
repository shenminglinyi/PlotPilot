"""测试 JSON 修复功能"""
import json
import re
import pytest


def repair_json(content: str) -> str:
    """尝试修复常见的 JSON 格式问题"""
    if not content:
        return content

    content = re.sub(r',\s*}', '}', content)
    content = re.sub(r',\s*]', ']', content)

    lines = content.split('\n')
    repaired_lines = []
    
    for line in lines:
        quote_positions = []
        i = 0
        while i < len(line):
            if line[i] == '\\' and i + 1 < len(line) and line[i+1] == '"':
                i += 2
                continue
            if line[i] == '"':
                quote_positions.append(i)
            i += 1
        
        if len(quote_positions) % 2 != 0:
            last_quote_pos = quote_positions[-1]
            line = line[:last_quote_pos+1] + '"' + line[last_quote_pos+1:]
        
        repaired_lines.append(line)
    
    content = '\n'.join(repaired_lines)

    stack = []
    in_string = False
    escape_next = False
    
    for i, char in enumerate(content):
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in '{[':
            stack.append(char)
        elif char in '}]':
            if stack:
                open_char = stack.pop()
                if (open_char == '{' and char != '}') or (open_char == '[' and char != ']'):
                    break
    
    if stack:
        closing_map = {'{': '}', '[': ']'}
        content = content.rstrip()
        for open_char in reversed(stack):
            content += closing_map[open_char]

    return content


class TestJsonRepair:
    """测试 JSON 修复功能"""

    def test_trailing_commas(self):
        """测试尾部逗号修复"""
        json_str = '''{
  "name": "test",
  "items": [1, 2, 3,],
  "value": 123,
}'''
        
        repaired = repair_json(json_str)
        result = json.loads(repaired)
        assert result['name'] == "test"
        assert result['items'] == [1, 2, 3]

    def test_unclosed_brackets(self):
        """测试未闭合括号修复"""
        json_str = '''{
  "parts": [
    {
      "title": "part1",
      "volumes": [
        {
          "title": "volume1"
        }
      ]
    }
  ]
'''
        
        repaired = repair_json(json_str)
        result = json.loads(repaired)
        assert result['parts'][0]['title'] == "part1"

    def test_multiple_issues(self):
        """测试多重问题修复"""
        json_str = '''{
  "title": "test",
  "items": [
    {"name": "item1",},
    {"name": "item2",}
  ],
'''
        
        repaired = repair_json(json_str)
        result = json.loads(repaired)
        assert result['title'] == "test"
        assert len(result['items']) == 2

    def test_truncated_json(self):
        """测试截断的 JSON"""
        json_str = '''{
  "parts": [
    {
      "title": "九零回响：破晓工厂",
      "volumes": [
        {
          "title": "卷一：广播台的暗雷",
          "theme": "阶层压迫与觉醒",
          "estimated_chapters": 3,
          "acts": [
            {
              "title": "act1",
              "description": "工人发现广播台秘'''
        
        repaired = repair_json(json_str)
        result = json.loads(repaired)
        assert result['parts'][0]['title'] == "九零回响：破晓工厂"
