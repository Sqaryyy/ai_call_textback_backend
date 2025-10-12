#!/usr/bin/env python3
"""
Script to index business knowledge for RAG
Usage: python index_business_knowledge.py [business_id]
If no business_id is provided, it will index all businesses
"""
import sys
import asyncio
from sqlalchemy.orm import Session

from app.config.database import SessionLocal
from app.services.ai.knowledge_indexer import KnowledgeIndexer
from app.models.business import Business


async def index_business_knowledge(business_id: str = None):
    """Index knowledge for a specific business or all businesses"""
    db: Session = SessionLocal()
    indexer = KnowledgeIndexer()

    try:
        if business_id:
            # Index single business
            print(f"\n📚 Indexing knowledge for business: {business_id}")
            print("=" * 60)

            # Verify business exists
            business = db.query(Business).filter(Business.id == business_id).first()
            if not business:
                print(f"❌ Error: Business with ID {business_id} not found")
                return

            print(f"Business: {business.name}")
            print(f"Phone: {business.phone_number}")
            print()

            result = await indexer.index_single_business(
                business_id=business_id,
                db=db,
                force_reindex=True  # Delete old knowledge and reindex
            )

            print("\n" + "=" * 60)
            if result["success"]:
                print(f"✅ SUCCESS: Indexed {result['indexed_count']} knowledge chunks")
            else:
                print(f"❌ FAILED: {result['message']}")

        else:
            # Index all businesses
            print("\n📚 Indexing knowledge for ALL businesses")
            print("=" * 60)

            result = await indexer.index_all_businesses(
                db=db,
                force_reindex=True
            )

            print("\n" + "=" * 60)
            print(f"Total businesses: {result['total_businesses']}")
            print(f"✅ Successful: {result['successful']}")
            print(f"❌ Failed: {result['failed']}")
            print()

            if result.get("details"):
                print("Details:")
                for detail in result["details"]:
                    status = "✅" if detail["success"] else "❌"
                    print(f"  {status} {detail['business_name']}: {detail['indexed_count']} chunks")

        # Show overall status
        print("\n" + "=" * 60)
        print("📊 Overall Indexing Status")
        print("=" * 60)

        status = indexer.get_indexing_status(db)
        if status["success"]:
            print(f"Active businesses: {status['total_active_businesses']}")
            print(f"Indexed businesses: {status['indexed_businesses']}")
            print(f"Not indexed: {status['not_indexed']}")
            print(f"Total knowledge chunks: {status['total_knowledge_chunks']}")
            print(f"Avg chunks per business: {status['average_chunks_per_business']}")

        print("\n✅ Done!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def main():
    """Main entry point"""
    business_id = None

    if len(sys.argv) > 1:
        business_id = sys.argv[1]
        print(f"Indexing business: {business_id}")
    else:
        print("No business ID provided. Indexing ALL businesses...")

    # Run async function
    asyncio.run(index_business_knowledge(business_id))


if __name__ == "__main__":
    main()