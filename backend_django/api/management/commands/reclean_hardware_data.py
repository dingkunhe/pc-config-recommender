import json
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Hardware, ApiConfig
from api.hardware_cleaner import infer_category_key, infer_brand, infer_model, normalize_text
from api.llm_client import invoke_with_config


class Command(BaseCommand):
    help = '临时程序：对现有硬件数据执行重新清洗（类别/品牌/型号规范化）'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='仅预览变更，不写入数据库')
        parser.add_argument('--limit', type=int, default=0, help='仅处理前 N 条记录（0 表示全部）')
        parser.add_argument('--id-start', type=int, default=0, help='仅处理 ID >= 该值 的记录')
        parser.add_argument('--id-end', type=int, default=0, help='仅处理 ID <= 该值 的记录')
        parser.add_argument('--use-ai', action='store_true', help='启用推荐系统API对类别进行辅助分析')
        parser.add_argument('--ai-min-confidence', type=int, default=70, help='AI最小置信度阈值(0-100)，默认70')

    @staticmethod
    def _extract_json_from_text(text):
        if not text:
            return None
        txt = str(text).strip()
        try:
            return json.loads(txt)
        except Exception:
            pass

        m = re.search(r'\{[\s\S]*\}', txt)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    def _ai_infer_category(self, api_configs, hw, current_category):
        allowed = [c[0] for c in Hardware.CATEGORY_CHOICES]
        user_content = (
            f"请判断以下硬件最合适的类别（只能从指定枚举中选）。\n"
            f"类别枚举: {allowed}\n"
            f"当前类别: {current_category}\n"
            f"name: {normalize_text(hw.name)}\n"
            f"brand: {normalize_text(hw.brand)}\n"
            f"model: {normalize_text(hw.model)}\n"
            f"description: {normalize_text(hw.description)[:1400]}\n\n"
            f"仅输出JSON，不要额外文字，格式："
            f"{{\"category\":\"...\",\"confidence\":0-100,\"reason\":\"...\"}}"
        )

        system_prompt = (
            "你是电脑硬件数据清洗审校员。"
            "请特别避免把笔记本电脑误判为CPU/GPU/主板等配件。"
            "若数据明显是手机/非PC硬件，可判定为other。"
        )

        payload_template = {
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_content}
            ],
            'temperature': 0.1
        }

        for config in api_configs:
            try:
                ok, content = invoke_with_config(
                    config=config,
                    messages=payload_template.get('messages', []),
                    temperature=payload_template.get('temperature', 0.1),
                    timeout=35,
                )
                if not ok:
                    continue
                parsed = self._extract_json_from_text(content)
                if not isinstance(parsed, dict):
                    continue

                category = str(parsed.get('category', '')).strip().lower()
                try:
                    confidence = int(parsed.get('confidence', 0))
                except Exception:
                    confidence = 0
                reason = str(parsed.get('reason', '') or '').strip()

                if category in allowed:
                    return {
                        'ok': True,
                        'category': category,
                        'confidence': confidence,
                        'reason': reason,
                        'api_name': config.name,
                    }
            except Exception:
                continue

        return {'ok': False}

    def handle(self, *args, **options):
        dry_run = bool(options.get('dry_run'))
        limit = int(options.get('limit') or 0)
        id_start = int(options.get('id_start') or 0)
        id_end = int(options.get('id_end') or 0)
        use_ai = bool(options.get('use_ai'))
        ai_min_confidence = int(options.get('ai_min_confidence') or 70)

        qs = Hardware.objects.all().order_by('id')
        if id_start > 0:
            qs = qs.filter(id__gte=id_start)
        if id_end > 0:
            qs = qs.filter(id__lte=id_end)
        if limit > 0:
            qs = qs[:limit]

        api_configs = []
        if use_ai:
            api_configs = list(ApiConfig.objects.filter(is_active=True).order_by('-is_primary', 'id'))
            if not api_configs:
                self.stdout.write(self.style.WARNING('未找到可用推荐系统API配置，将回退到规则清洗'))
                use_ai = False

        total = 0
        updated = 0
        category_changed = 0
        brand_changed = 0
        model_changed = 0
        name_changed = 0

        self.stdout.write(self.style.NOTICE('开始执行硬件数据重新清洗...'))
        self.stdout.write(self.style.NOTICE(f"模式: {'仅预览(dry-run)' if dry_run else '写入数据库'}"))
        if use_ai:
            self.stdout.write(self.style.NOTICE(f"AI分析: 开启（置信度阈值: {ai_min_confidence}）"))

        with transaction.atomic():
            for hw in qs:
                total += 1

                old_name = hw.name
                old_brand = hw.brand or ''
                old_model = hw.model or ''
                old_category = hw.category or 'other'

                new_name = normalize_text(old_name)
                new_model = normalize_text(old_model)
                new_brand = normalize_text(old_brand)

                if not new_model:
                    new_model = infer_model(new_name)
                if not new_brand:
                    new_brand = infer_brand(new_name, new_model)

                new_category = infer_category_key(new_name, hw.description or '', old_category)

                if use_ai:
                    ai_result = self._ai_infer_category(api_configs, hw, old_category)
                    if ai_result.get('ok') and ai_result.get('confidence', 0) >= ai_min_confidence:
                        ai_category = ai_result.get('category')
                        if ai_category:
                            new_category = ai_category

                changed_fields = []
                if new_name != old_name:
                    changed_fields.append('name')
                    name_changed += 1
                if new_brand != old_brand:
                    changed_fields.append('brand')
                    brand_changed += 1
                if new_model != old_model:
                    changed_fields.append('model')
                    model_changed += 1
                if new_category != old_category:
                    changed_fields.append('category')
                    category_changed += 1

                if changed_fields:
                    updated += 1
                    ai_tag = ''
                    if use_ai:
                        ai_tag = ' [AI分析已启用]'
                    self.stdout.write(
                        f"[ID={hw.id}] {old_category} -> {new_category} | {old_name}{ai_tag}"
                    )
                    if not dry_run:
                        hw.name = new_name
                        hw.brand = new_brand
                        hw.model = new_model
                        hw.category = new_category
                        hw.save(update_fields=['name', 'brand', 'model', 'category'])

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS('硬件数据重新清洗完成'))
        self.stdout.write(
            self.style.SUCCESS(
                f"总记录: {total} | 发生变更: {updated} | 类别变更: {category_changed} | 品牌变更: {brand_changed} | 型号变更: {model_changed} | 名称规范化: {name_changed}"
            )
        )
