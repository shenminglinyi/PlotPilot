"""测试连续规划服务的 JSON 解析功能"""
import json
import pytest

from application.blueprint.services.continuous_planning_service import (
    ContinuousPlanningService,
)


class MockService:
    """Mock service for testing"""
    _repair_json = ContinuousPlanningService._repair_json
    _parse_llm_response = ContinuousPlanningService._parse_llm_response


@pytest.fixture
def service():
    return MockService()


class TestContinuousPlanningJson:
    """测试 JSON 解析功能"""

    def test_normal_json(self, service):
        """测试正常 JSON"""
        normal_response = json.dumps({
            "parts": [
                {
                    "title": "第一部分",
                    "volumes": [
                        {
                            "title": "卷一",
                            "theme": "觉醒",
                            "estimated_chapters": 3
                        }
                    ]
                }
            ]
        })
        
        result = service._parse_llm_response(normal_response)
        assert result['parts'][0]['title'] == "第一部分"

    def test_markdown_code_block(self, service):
        """测试带 Markdown 代码块"""
        markdown_response = '''这是一个故事规划：

```json
{
  "parts": [
    {
      "title": "九零回响",
      "volumes": [
        {
          "title": "卷一：破晓",
          "theme": "觉醒",
          "estimated_chapters": 3
        }
      ]
    }
  ]
}
```

希望这个规划对你有帮助。'''
        
        result = service._parse_llm_response(markdown_response)
        assert result['parts'][0]['title'] == "九零回响"

    def test_truncated_json(self, service):
        """测试截断的 JSON（真实错误场景）"""
        truncated_response = '''{
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
              "title": "第一幕：暗流涌动",
              "description": "工人发现广播台秘密"
            }
          ]
        }
      ]
    }
  ]
'''
        
        result = service._parse_llm_response(truncated_response)
        assert result['parts'][0]['title'] == "九零回响：破晓工厂"
        assert len(result['parts'][0]['volumes']) == 1

    def test_trailing_commas(self, service):
        """测试带尾部逗号"""
        trailing_comma_response = '''{
  "parts": [
    {
      "title": "test",
      "volumes": [
        {
          "title": "volume1",
          "theme": "theme1",
        }
      ],
    }
  ],
}'''
        
        result = service._parse_llm_response(trailing_comma_response)
        assert result['parts'][0]['title'] == "test"

    def test_unclosed_string(self, service):
        """测试未闭合的字符串（极端场景，可能失败）"""
        unclosed_string_response = '''{
  "parts": [
    {
      "title": "九零回响：破晓工厂",
      "description": "这是一个关于工人觉醒的故事，
      "volumes": []
    }
  ]
}'''
        
        with pytest.raises((ValueError, json.JSONDecodeError)):
            service._parse_llm_response(unclosed_string_response)
