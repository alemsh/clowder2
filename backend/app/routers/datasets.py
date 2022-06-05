import datetime
import io
import os
from typing import List, Optional
import zipfile
import shutil

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from fastapi import Form
from minio import Minio
from pymongo import MongoClient

from app import keycloak_auth
from app import dependencies
from app.keycloak_auth import get_user, get_current_user
from app.config import settings
from app.models.datasets import (
    DatasetBase,
    DatasetIn,
    DatasetDB,
    DatasetOut,
    DatasetPatch,
)
from app.models.files import FileIn, FileOut, FileVersion, FileDB
from app.models.folders import FolderOut, FolderIn, FolderDB
from app.models.pyobjectid import PyObjectId
from app.models.users import UserOut
from app.models.extractors import ExtractorIn
from app.models.metadata import (
    MongoDBRef,
    MetadataAgent,
    MetadataIn,
    MetadataDB,
    MetadataOut,
    MetadataPatch,
    validate_context,
    patch_metadata
)

router = APIRouter()

clowder_bucket = os.getenv("MINIO_BUCKET_NAME", "clowder")

async def process_folders_zip_upload(
    path_to_folder: str,
    dataset_id: str,
    current_folder_id: str,
    user=Depends(get_current_user),
    db: MongoClient = Depends(dependencies.get_db),
    fs: Minio = Depends(dependencies.get_fs),
):
    contents = os.listdir(path_to_folder)
    for item in contents:
        if item != '.DS_Store':
            path_to_item = os.path.join(path_to_folder, item)
            if os.path.isdir(path_to_item):
                if current_folder_id == "":
                    folder_dict = {'dataset_id': dataset_id, 'name': item}
                else:
                    folder_dict = {'dataset_id': dataset_id, 'name': item, 'parent_folder': current_folder_id}
                folder_db = FolderDB(**folder_dict, author=user)
                new_folder = await db["folders"].insert_one(folder_db.to_mongo())
                found = await db["folders"].find_one({"_id": new_folder.inserted_id})
                result = await process_folders_zip_upload(path_to_item, dataset_id, new_folder.inserted_id, user, db, fs)
            if os.path.isfile(path_to_item):
                with open(path_to_item, 'rb') as fh:
                    if current_folder_id != "":
                        fileDB = FileDB(name=item, creator=user, dataset_id=dataset_id, folder_id=current_folder_id)
                    else:
                        fileDB = FileDB(name=item, creator=user, dataset_id=dataset_id)
                    new_file = await db["files"].insert_one(fileDB.to_mongo())
                    new_file_id = new_file.inserted_id

                    response = fs.put_object(
                            settings.MINIO_BUCKET_NAME,
                            str(new_file_id),
                            fh,
                            length=-1,
                            part_size=settings.MINIO_UPLOAD_CHUNK_SIZE,
                        )  # async write chunk to minio

                    version_id = response.version_id
                    if version_id is None:
                        # TODO: This occurs in testing when minio is not running
                        version_id = 999999999
                    fileDB.version_id = version_id
                    fileDB.version_num = 1
                    print(fileDB)



@router.post("", response_model=DatasetOut)
async def save_dataset(
    dataset_in: DatasetIn,
    user=Depends(keycloak_auth.get_current_user),
    db: MongoClient = Depends(dependencies.get_db),
):
    result = dataset_in.dict()
    dataset_db = DatasetDB(**dataset_in.dict(), author=user)
    new_dataset = await db["datasets"].insert_one(dataset_db.to_mongo())
    found = await db["datasets"].find_one({"_id": new_dataset.inserted_id})
    dataset_out = DatasetOut.from_mongo(found)
    return dataset_out


@router.get("", response_model=List[DatasetOut])
async def get_datasets(
    user_id=Depends(get_user),
    db: MongoClient = Depends(dependencies.get_db),
    skip: int = 0,
    limit: int = 2,
    mine: bool = False,
):
    datasets = []
    if mine:
        for doc in (
            await db["datasets"]
            .find({"author.email": user_id})
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        ):
            datasets.append(DatasetOut.from_mongo(doc))
    else:
        for doc in (
            await db["datasets"].find().skip(skip).limit(limit).to_list(length=limit)
        ):
            datasets.append(DatasetOut.from_mongo(doc))
    return datasets


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(dataset_id: str, db: MongoClient = Depends(dependencies.get_db)):
    if (
        dataset := await db["datasets"].find_one({"_id": ObjectId(dataset_id)})
    ) is not None:
        return DatasetOut.from_mongo(dataset)
    raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")


@router.get("/{dataset_id}/files")
async def get_dataset_files(
    dataset_id: str,
    folder_id: Optional[str] = None,
    db: MongoClient = Depends(dependencies.get_db),
):
    files = []
    if folder_id is None:
        async for f in db["files"].find(
            {"dataset_id": ObjectId(dataset_id), "folder_id": None}
        ):
            files.append(FileOut.from_mongo(f))
    else:
        async for f in db["files"].find(
            {
                "dataset_id": ObjectId(dataset_id),
                "folder_id": ObjectId(folder_id),
            }
        ):
            files.append(FileOut.from_mongo(f))
    return files


@router.put("/{dataset_id}", response_model=DatasetOut)
async def edit_dataset(
    dataset_id: str,
    dataset_info: DatasetBase,
    db: MongoClient = Depends(dependencies.get_db),
    user_id=Depends(get_user),
):
    if (
        dataset := await db["datasets"].find_one({"_id": ObjectId(dataset_id)})
    ) is not None:
        # TODO: Refactor this with permissions checks etc.
        ds = dict(dataset_info) if dataset_info is not None else {}
        user = await db["users"].find_one({"_id": ObjectId(user_id)})
        ds["author"] = UserOut(**user)
        ds["modified"] = datetime.datetime.utcnow()
        try:
            dataset.update(ds)
            await db["datasets"].replace_one(
                {"_id": ObjectId(dataset_id)}, DatasetDB(**dataset).to_mongo()
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=e.args[0])
        return DatasetOut.from_mongo(dataset)
    raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")


@router.patch("/{dataset_id}", response_model=DatasetOut)
async def patch_dataset(
    dataset_id: str,
    dataset_info: DatasetPatch,
    user_id=Depends(get_user),
    db: MongoClient = Depends(dependencies.get_db),
):
    if (
        dataset := await db["datasets"].find_one({"_id": ObjectId(dataset_id)})
    ) is not None:
        # TODO: Refactor this with permissions checks etc.
        ds = dict(dataset_info) if dataset_info is not None else {}
        user = await db["users"].find_one({"_id": ObjectId(user_id)})
        ds["author"] = UserOut(**user)
        ds["modified"] = datetime.datetime.utcnow()
        try:
            dataset.update((k, v) for k, v in ds.items() if v is not None)
            await db["datasets"].replace_one(
                {"_id": ObjectId(dataset_id)}, DatasetDB(**dataset).to_mongo()
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=e.args[0])
        return DatasetOut.from_mongo(dataset)


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    db: MongoClient = Depends(dependencies.get_db),
    fs: Minio = Depends(dependencies.get_fs),
):
    if (await db["datasets"].find_one({"_id": ObjectId(dataset_id)})) is not None:
        # delete dataset first to minimize files/folder being uploaded to a delete dataset
        await db["datasets"].delete_one({"_id": ObjectId(dataset_id)})
        async for file in db["files"].find({"dataset_id": ObjectId(dataset_id)}):
            fs.remove_object(clowder_bucket, str(file))
        files_deleted = await db.files.delete_many({"dataset_id": ObjectId(dataset_id)})
        folders_delete = await db["folders"].delete_many(
            {"dataset_id": ObjectId(dataset_id)}
        )
        return {"deleted": dataset_id}
    else:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")


@router.post("/{dataset_id}/folders", response_model=FolderOut)
async def add_folder(
    dataset_id: str,
    folder_in: FolderIn,
    user=Depends(get_current_user),
    db: MongoClient = Depends(dependencies.get_db),
):
    folder_dict = folder_in.dict()
    folder_db = FolderDB(
        **folder_in.dict(), author=user, dataset_id=PyObjectId(dataset_id)
    )
    parent_folder = folder_in.parent_folder
    if parent_folder is not None:
        folder = await db["folders"].find_one({"_id": ObjectId(parent_folder)})
        if folder is None:
            raise HTTPException(
                status_code=400, detail=f"Parent folder {parent_folder} not found"
            )
    new_folder = await db["folders"].insert_one(folder_db.to_mongo())
    found = await db["folders"].find_one({"_id": new_folder.inserted_id})
    folder_out = FolderOut.from_mongo(found)
    return folder_out


@router.get("/{dataset_id}/folders")
async def get_dataset_folders(
    dataset_id: str,
    parent_folder: Optional[str] = None,
    db: MongoClient = Depends(dependencies.get_db),
):
    folders = []
    if parent_folder is None:
        async for f in db["folders"].find(
            {"dataset_id": ObjectId(dataset_id), "parent_folder": None}
        ):
            folders.append(FolderDB.from_mongo(f))
    else:
        async for f in db["folders"].find(
            {
                "dataset_id": ObjectId(dataset_id),
                "parent_folder": ObjectId(parent_folder),
            }
        ):
            folders.append(FolderDB.from_mongo(f))
    return folders


@router.delete("/{dataset_id}/folder/{folder_id}")
async def delete_folder(
    dataset_id: str,
    folder_id: str,
    db: MongoClient = Depends(dependencies.get_db),
    fs: Minio = Depends(dependencies.get_fs),
):
    if (await db["folder"].find_one({"_id": ObjectId(dataset_id)})) is not None:
        async for f in db["files"].find({"dataset_id": ObjectId(dataset_id)}):
            fs.remove_object(clowder_bucket, str(f))
        await db["datasets"].delete_one({"_id": ObjectId(dataset_id)})
        return {"deleted": dataset_id}
    else:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")


@router.post("/{dataset_id}/files", response_model=FileOut)
async def save_file(
    dataset_id: str,
    folder_id: Optional[str] = Form(None),
    user=Depends(get_current_user),
    db: MongoClient = Depends(dependencies.get_db),
    fs: Minio = Depends(dependencies.get_fs),
    file: UploadFile = File(...),
):
    if (
        dataset := await db["datasets"].find_one({"_id": ObjectId(dataset_id)})
    ) is not None:
        if user is None:
            raise HTTPException(
                status_code=401, detail=f"User not found. Session might have expired."
            )

        dataset = await db["datasets"].find_one({"_id": ObjectId(dataset_id)})
        if dataset is None:
            raise HTTPException(
                status_code=404, detail=f"Dataset {dataset_id} not found"
            )
        fileDB = FileDB(name=file.filename, creator=user, dataset_id=dataset["_id"])

        if folder_id is not None:
            if (
                folder := await db["folders"].find_one({"_id": ObjectId(folder_id)})
            ) is not None:
                fileDB.folder_id = folder.id
            else:
                raise HTTPException(
                    status_code=404, detail=f"Folder {folder_id} not found"
                )

        new_file = await db["files"].insert_one(fileDB.to_mongo())
        new_file_id = new_file.inserted_id

        # Use unique ID as key for Minio and get initial version ID
        version_id = None
        while content := file.file.read(
            settings.MINIO_UPLOAD_CHUNK_SIZE
        ):  # async read chunk
            response = fs.put_object(
                settings.MINIO_BUCKET_NAME,
                str(new_file_id),
                io.BytesIO(content),
                length=-1,
                part_size=settings.MINIO_UPLOAD_CHUNK_SIZE,
            )  # async write chunk to minio
            version_id = response.version_id
        if version_id is None:
            # TODO: This occurs in testing when minio is not running
            version_id = 999999999
        fileDB.version_id = version_id
        fileDB.version_num = 1
        print(fileDB)
        await db["files"].replace_one({"_id": ObjectId(new_file_id)}, fileDB.to_mongo())

        # Add FileVersion entry and update file
        new_version = FileVersion(
            version_id=version_id,
            file_id=new_file_id,
            creator=user,
        )
        await db["file_versions"].insert_one(new_version.to_mongo())
        return fileDB
    else:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")


@router.post("/createFromZip", response_model=DatasetOut)
async def create_dataset_from_zip(
    user=Depends(get_current_user),
    db: MongoClient = Depends(dependencies.get_db),
    fs: Minio = Depends(dependencies.get_fs),
    file: UploadFile = File(...),
):
    if file.endswith('.zip') == False:
        raise HTTPException(status_code=404, detail=f"File is not a zip file")
    with open(file.filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    unzipped_folder_name = file.filename.rstrip(".zip")
    path_to_zip = os.path.join(os.getcwd(), file.filename)

    with zipfile.ZipFile(path_to_zip, 'r') as zip:
        zip.extractall(os.getcwd())

    macos_folder = os.path.join(os.getcwd(), '__MACOSX')
    if os.path.exists(macos_folder):
        shutil.rmtree(macos_folder)

    dataset_name = unzipped_folder_name
    dataset_description = unzipped_folder_name
    ds_dict = {'name': dataset_name, 'description': dataset_description}
    dataset_db = DatasetDB(**ds_dict, author=user)
    new_dataset = await db["datasets"].insert_one(dataset_db.to_mongo())
    found = await db["datasets"].find_one({"_id": new_dataset.inserted_id})
    result = await process_folders_zip_upload(unzipped_folder_name, new_dataset.inserted_id, "", user, db, fs)

    try:
        os.remove(file.filename)
    except Exception as e:
        print(e)
        print("could not delete", file.filename)
    try:
        shutil.rmtree(unzipped_folder_name)
    except Exception as e:
        print(e)
        print("could not delete", file.filename)
    dataset_out = DatasetOut.from_mongo(found)
    return dataset_out
