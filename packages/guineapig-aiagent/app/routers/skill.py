"""Skill 解析路由"""

from fastapi import APIRouter

from app.core.log import logger
from app.schemas.base_models import success_response, error_response
from app.schemas.skill_models import SkillProcessRequest
from app.services.skill_service import process_skill_zip

router = APIRouter(prefix="/guineapig-aiagent/skill", tags=["skill"])


@router.post("/process")
def process_skill(request: SkillProcessRequest):
    """
    解析 Skill zip 文件。

    从 S3 下载指定的 zip 文件，解压并解析 SKILL.md，返回 skill 元数据。

    请求参数:
        objectKey (str): S3 对象键，格式 skills/{user_id}/{date}/{skill-name}.zip
    """
    logger.info(f"[Skill] 收到解析请求: objectKey={request.objectKey}")

    try:
        result = process_skill_zip(request.objectKey)
        return success_response(data=result)
    except ValueError as e:
        logger.error(f"[Skill] 参数错误: {e}")
        return error_response(message=str(e), code=400)
    except Exception as e:
        logger.error(f"[Skill] 处理异常: {e}")
        return error_response(message=f"处理失败: {str(e)}", code=500)
