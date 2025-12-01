# UI 用户界面模块功能说明

## 模块概述
UI模块提供图形用户界面组件，主要用于显示用户交互对话框和消息确认窗口。

## 文件功能说明

### 1. `__init__.py` - 模块初始化文件
- **功能**：模块包初始化定义
- **作用**：
  - 定义模块的公共接口和导出类
  - 提供模块级别的导入控制
  - 声明 `MessageBox` 类为模块的主要导出对象
- **特性**：简洁的模块结构，便于其他模块导入使用

### 2. `message_box.py` - 消息确认窗口组件
- **功能**：提供带有"重试"和"放弃"按钮的确认对话框
- **核心组件**：
  - **MessageBox类**：消息确认窗口主类
  - **窗口管理**：创建、显示、关闭消息窗口
  - **按钮控制**：自定义按钮显示状态和文本
  - **线程支持**：支持同步和异步调用模式
- **主要特性**：
  - **自定义按钮**：可配置是否显示重试/放弃按钮
  - **文本定制**：支持自定义按钮显示文本
  - **线程安全**：支持主线程和子线程调用
  - **窗口居中**：自动计算窗口位置并居中显示
  - **键盘支持**：支持回车键和ESC键操作
  - **无边框设计**：隐藏标题栏，提供简洁界面

## 核心功能详解

### MessageBox类主要方法

#### 1. 构造函数
```python
def __init__(self, title: str = "确认", 
             show_retry: bool = True, show_cancel: bool = True,
             retry_text: str = "重试", cancel_text: str = "放弃")
```
- **title**：窗口标题
- **show_retry**：是否显示重试按钮
- **show_cancel**：是否显示放弃按钮
- **retry_text**：重试按钮显示文本
- **cancel_text**：放弃按钮显示文本

#### 2. 显示方法
```python
def show(self, msg: str, callback: Optional[Callable] = None) -> Optional[str]
```
- **msg**：要显示的消息内容
- **callback**：回调函数，用户点击按钮时调用
- **返回值**：同步调用返回按钮类型，异步调用返回None

#### 3. 等待结果方法
```python
def wait_for_result(self) -> str
```
- 等待异步调用的结果
- 返回按钮类型（'retry'或'cancel'）

### 便捷函数
```python
def show_message_box(msg: str, title: str = "确认",
                    show_retry: bool = True, show_cancel: bool = True,
                    retry_text: str = "重试", cancel_text: str = "放弃") -> str
```
- 快速显示消息确认窗口的便捷函数
- 简化了MessageBox类的使用流程

## 使用场景

### 1. 同步调用（主线程）
```python
from local_agent.ui import MessageBox

# 创建消息框实例
msg_box = MessageBox(title="更新确认", show_retry=True, show_cancel=True)

# 同步显示并等待结果
result = msg_box.show("检测到新版本，是否立即更新？")

if result == "retry":
    # 用户点击了重试按钮
    print("开始更新...")
else:
    # 用户点击了放弃按钮
    print("取消更新")
```

### 2. 异步调用（子线程）
```python
from local_agent.ui import MessageBox
import threading

def update_handler():
    # 在子线程中创建消息框
    msg_box = MessageBox(title="更新确认")
    
    # 异步显示
    msg_box.show("检测到新版本，是否立即更新？")
    
    # 等待用户操作
    result = msg_box.wait_for_result()
    
    if result == "retry":
        print("开始更新...")

# 在子线程中执行
thread = threading.Thread(target=update_handler)
thread.start()
```

### 3. 使用便捷函数
```python
from local_agent.ui.message_box import show_message_box

# 快速显示消息框
result = show_message_box(
    msg="检测到新版本，是否立即更新？",
    title="更新确认",
    show_retry=True,
    show_cancel=True
)

print(f"用户选择了：{result}")
```

## 技术特点

- **基于tkinter**：使用Python标准GUI库，无需额外依赖
- **跨平台兼容**：支持Windows、Linux、macOS等操作系统
- **线程安全**：正确处理多线程环境下的GUI操作
- **用户友好**：简洁的界面设计，良好的用户体验
- **高度可定制**：支持多种自定义选项

## 注意事项

1. **线程限制**：GUI操作必须在主线程中执行，异步调用会自动处理线程切换
2. **窗口焦点**：消息框会获取焦点，确保用户必须响应
3. **无边框设计**：窗口没有标题栏，用户只能通过按钮关闭
4. **自动居中**：窗口会自动计算屏幕位置并居中显示
5. **键盘支持**：支持回车键（重试）和ESC键（放弃）操作