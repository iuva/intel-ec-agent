#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API route definitions
Define all FastAPI interface routes
"""

from fastapi import APIRouter, Body
from pydantic import BaseModel
from typing import Dict, Any

from ..config import get_config
from ..logger import get_logger
from local_agent.utils.http_client import http_post, http_put
from ..utils.timer_utils import clear_timeout, set_timeout
from ..core.global_cache import cache, set_agent_status, set_dmr_info, get_agent_status_by_key, get_dmr_upload_task_id, get_dmr_info, set_dmr_upload_task_id, get_ek_test_info
from ..core.constants import HARDWARE_INFO_TASK_ID
from ..core.app_update import upload_dmr
from ..core.host_init import VNC, EK, DMR
from ..utils.message_tool import show_message_box

router = APIRouter()
logger = get_logger(__name__)
config = get_config()

class EKResultEvent(BaseModel):
    """EK result reporting request model"""
    type: str
    status_code: str
    details: Dict[str, Any]

class EKResultRequest(BaseModel):
    """EK result reporting request model"""
    tool: str
    timestamp: str
    session_id: str
    event: EKResultEvent

class DMRResultDetails(BaseModel):
    """EK result reporting request model"""
    mode: str
    output_file: str
    output_data: Dict[str, Any]

class DMRResultEvent(BaseModel):
    """EK result reporting request model"""
    type: str
    status_code: str
    details: DMRResultDetails

class DMRResultPayload(BaseModel):
    """EK result reporting request model"""
    tool: str
    timestamp: str
    event: DMRResultEvent

class DMRResultRequest(BaseModel):
    """EK result reporting request model"""
    Payload: DMRResultPayload

class CommonResponse(BaseModel):
    """Common response model"""
    code: int  # 0-Success, 1-Failure
    msg: str



@router.post("/ek/start/result", response_model=CommonResponse)
async def ek_start_result(request: EKResultRequest):
    """
    EK start result reporting interface
    
    
    """
    try:

        logger.debug(f"Start result report request: {request}")
        event = request.event

        details = event.details

        # Start result reporting
        case_res = http_post(url="/host/agent/testcase/report", data={
            "tc_id": details.get('tc_id', ''),
            # "state": 1,
            "state": 1 if event.status_code == '0' else 3,
            "result_msg": "{\"code\":\"200\",\"msg\":\"ok\"}" if event.status_code == '0' else "{\"code\":\"400\",\"msg\":\"failed\"}",
            "log_url": "None",
        })

        if event.status_code == '1':
            # 3 秒后弹出提示，ek启动失败，是否重试
            set_timeout(3, ek_startup_failure)

            return CommonResponse(
                code=0,
                msg="success"
            )

        # due_time = TimeUtils.add_minutes_to_current(details.get('estimated_duration', 0))

        # Report test case expected end time
        res = http_put(url="/host/agent/testcase/due-time", data={
            "tc_id": details.get('tc_id', ''),
            "due_time": int(details.get('estimated_duration', 0))
        })

        logger.debug(f"Start result report response: {res}")
        
        res_data = res.get('data', {})
        res_code = res_data.get('code', 0)
        if res_code != 200:
            logger.error(f"Start result report failed: {res}")

        set_agent_status(test=True)
        return CommonResponse(
            code=res_data.get('code'),
            msg=res_data.get('message')
        )

    except Exception as e:
        logger.error(f"Error occurred while processing start result report: {str(e)}")
        return CommonResponse(
            code=1,
            msg=f"Processing failed: {str(e)}"
        )

def ek_startup_failure():
    """
    EK startup failure prompt
    """
    result = show_message_box(
        msg=f"EK startup failed. Do you want to retry?",
        title="Prompt",
        confirm_text="Retry",
        cancel_show=True
    )
    logger.info(f"User choice: {result}")

    EK.test_kill()
    if result == "Retry":
        import time
        time.sleep(10)
        
        test_info = get_ek_test_info()
        EK.start_test(test_info['tc_id'], test_info['cycle_name'], test_info['user_name'])
    else:
        set_agent_status(test=False)



@router.post("/ek/test/result", response_model=CommonResponse)
async def report_tool_result(request: EKResultRequest):
    """
    EK result reporting interface
    
    This interface waits for EK calls, and after being called, it reports the organized information to the server
    """
    try:

        event = request.event

        details = event.details

        # Test result reporting
        res = http_post(url="/host/agent/testcase/report", data={
            "tc_id": details.get('tc_id', ''),
            "state": 2 if event.status_code == '0' else 3,
            "result_msg": "{\"code\":\"200\",\"msg\":\"ok\"}",
            "log_url": "None",
        })

        logger.debug(f"Test result report response: {res}")
        
        res_data = res.get('data', {})
        res_code = res_data.get('code', 0)
        if res_code != 200:
            logger.error(f"Test result report failed: {res}")

            return CommonResponse(
                code=res_data.get('code'),
                msg=res_data.get('message')
            )
        
        # Report hardware info
        if event.status_code == '0':
            upload_dmr()
            set_agent_status(test=False)

            test = get_agent_status_by_key('vnc')
            if test:
                set_timeout(5, is_close_vnc)

        return CommonResponse(
            code=res_data.get('code'),
            msg=res_data.get('message')
        )

    except Exception as e:
        logger.error(f"Error occurred while processing result report: {str(e)}")
        return CommonResponse(
            code=1,
            msg=f"Processing failed: {str(e)}"
        )


def is_close_vnc():
    result = show_message_box(
        msg=f"The test has ended. Do you want to close the VNC connection",
        title="Prompt",
        confirm_text="Close",
        cancel_show=True,
        confirm_timeout=10
    )
    logger.info(f"User choice: {result}")

    if result == "Close":
        VNC.disconnect()
        EK.test_kill()

@router.get("/ek/log/last", response_model=CommonResponse)
async def report_dmr_result(tc_id: str):
    """
    Hardware info result reporting interface
    
    This interface waits for EK calls, and after being called, it reports the organized information to the server
    """
    file_path = logger.get_latest_replica_file()

    logger.info(f"Latest log file path: {file_path}")
    if not file_path:
        return CommonResponse(
            code=1,
            msg="No log file found"
        )

    return CommonResponse(
        code=0,
        msg="success",
        data={
            "log_file_path": file_path
        }
    )


@router.post("/dmr/info/result", response_model=CommonResponse)
async def report_dmr_result(request: DMRResultPayload):
    """
    Hardware info result reporting interface
    
    This interface waits for EK calls, and after being called, it reports the organized information to the server
    """
    try:

        # Whether successful
        if request.event.status_code == "0":
            # Clear hardware info retrieval timed task
            task_id = cache.get(HARDWARE_INFO_TASK_ID)
            if task_id:
                clear_timeout(task_id)
                cache.set(HARDWARE_INFO_TASK_ID, '')


        body = {
            "name": request.tool,
            "type": request.event.status_code,
            "dmr_config": request.event.details.output_data,
        }

        set_dmr_info(body)

        # If in test then do not report, call logic is in test end reporting
        agent_status = get_agent_status_by_key('test')
        logger.info(f"Test status: {agent_status}{type(agent_status)}")
        if not agent_status:
            # Report hardware info
            logger.info("Starting call: upload_dmr")
            upload_dmr()

        DMR.kill_dmr()

        return CommonResponse(
            code=0,
            msg="success"
        )
        
        
    except Exception as e:
        logger.error(f"Error occurred while processing result report: {str(e)}")
        return CommonResponse(
            code=1,
            msg=f"Processing failed: {str(e)}"
        )

