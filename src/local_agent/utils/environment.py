"""
环境工具类 - 用于判断当前运行环境

提供开发环境和生产环境的判断功能，基于不同的运行模式进行环境检测。
"""

import sys
import os
from pathlib import Path

from ..logger import get_logger

logger = get_logger(__name__)


class Environment:
    """环境工具类，提供环境判断功能"""
    
    @staticmethod
    def is_development() -> bool:
        """
        判断当前是否处于开发环境
        
        开发环境判断标准：
        1. 不是PyInstaller打包的可执行文件
        2. 存在源码目录结构
        3. 可以访问Python源码文件
        
        Returns:
            bool: 如果是开发环境返回True，否则返回False
        """
        try:
            # 检查是否为PyInstaller打包的可执行文件
            if getattr(sys, 'frozen', False):
                logger.debug("检测到PyInstaller打包环境，判断为生产环境")
                return False
            
            # 检查是否存在源码目录结构
            current_file_path = Path(__file__).resolve()
            project_root = current_file_path.parent.parent.parent.parent  # 回溯到项目根目录
            
            # 检查是否存在src目录和local_agent包
            src_dir = project_root / "src"
            local_agent_dir = src_dir / "local_agent"
            
            if local_agent_dir.exists() and local_agent_dir.is_dir():
                # 检查是否存在__init__.py文件（Python包标识）
                init_file = local_agent_dir / "__init__.py"
                if init_file.exists():
                    logger.debug("检测到源码目录结构，判断为开发环境")
                    return True
            
            # 检查是否存在setup.py或requirements.txt（开发环境标志）
            setup_file = project_root / "setup.py"
            requirements_file = project_root / "requirements.txt"
            
            if setup_file.exists() or requirements_file.exists():
                logger.debug("检测到开发配置文件，判断为开发环境")
                return True
                
            logger.debug("未检测到开发环境特征，判断为生产环境")
            return False
            
        except Exception as e:
            logger.warning(f"环境检测异常，默认判断为生产环境: {e}")
            return False
    
    @staticmethod
    def is_production() -> bool:
        """
        判断当前是否处于生产环境
        
        生产环境判断标准：
        1. 是PyInstaller打包的可执行文件
        2. 不存在源码目录结构
        3. 运行在打包后的环境中
        
        Returns:
            bool: 如果是生产环境返回True，否则返回False
        """
        return not Environment.is_development()
    
    @staticmethod
    def get_environment_info() -> dict:
        """
        获取当前环境的详细信息
        
        Returns:
            dict: 包含环境信息的字典
        """
        info = {
            "is_development": Environment.is_development(),
            "is_production": Environment.is_production(),
            "is_frozen": getattr(sys, 'frozen', False),
            "executable": sys.executable,
            "python_version": sys.version,
            "platform": sys.platform,
            "current_file": __file__ if '__file__' in globals() else "Unknown"
        }
        
        # 添加项目路径信息
        try:
            current_path = Path(__file__).resolve()
            info["current_path"] = str(current_path)
            
            # 尝试找到项目根目录
            if Environment.is_development():
                project_root = current_path.parent.parent.parent.parent
                info["project_root"] = str(project_root)
                info["has_src_dir"] = (project_root / "src").exists()
                info["has_local_agent"] = (project_root / "src" / "local_agent").exists()
            else:
                # 生产环境下尝试获取可执行文件所在目录
                if getattr(sys, 'frozen', False):
                    info["executable_dir"] = str(Path(sys.executable).parent)
        except Exception as e:
            info["path_error"] = str(e)
        
        return info


# 便捷函数
def is_development() -> bool:
    """便捷函数：判断是否为开发环境"""
    return Environment.is_development()


def is_production() -> bool:
    """便捷函数：判断是否为生产环境"""
    return Environment.is_production()


def get_environment_info() -> dict:
    """便捷函数：获取环境信息"""
    return Environment.get_environment_info()


if __name__ == "__main__":
    """测试代码"""
    print("=== 环境检测测试 ===")
    
    # 测试环境判断
    print(f"开发环境: {is_development()}")
    print(f"生产环境: {is_production()}")
    
    # 显示详细环境信息
    info = get_environment_info()
    print("\n=== 环境详细信息 ===")
    for key, value in info.items():
        print(f"{key}: {value}")