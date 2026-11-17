from django.core.management.base import BaseCommand

from dvadmin.rag.kb import list_products
from dvadmin.rag.kb.ingest import ingest


class Command(BaseCommand):
    help = '为 RAG 产品建立/重建 PageIndex 树索引(调用 LLM 建树, 有耗时与成本)'

    def add_arguments(self, parser):
        parser.add_argument("--product", required=True, help="产品 ID, 或 all 表示全部")
        parser.add_argument("--force", action="store_true", help="已建索引的文档也重新提交")

    def handle(self, *args, **options):
        if options["product"] == "all":
            targets = [p["product_id"] for p in list_products()]
        else:
            targets = [options["product"]]

        for product_id in targets:
            ids = ingest(product_id, force=options["force"])
            self.stdout.write(self.style.SUCCESS(f"{product_id}: {ids}"))

        self.stdout.write(self.style.SUCCESS("done."))
