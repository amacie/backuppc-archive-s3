#!/usr/bin/env python3
# Manage archive is based on the code from the AWS Boto3 examples.
#
# Copyright 2010-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# This file is licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License. A copy of the
# License is located at
#
# http://aws.amazon.com/apache2.0/
#
# This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS
# OF ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
import argparse
import datetime
import json
import logging
import sqlobject
import dateutil.parser
import os

import rich.console
import boto3
from botocore.exceptions import ClientError

VALID_ACTIONS = ("list", "start_inventory", "status", "get_inventory", "history", "delete")
JOBS_DIR = "jobs"
JOB_STATUS_DB = f"{JOBS_DIR}/status.db"


class Job(sqlobject.SQLObject):
    job_id = sqlobject.StringCol()
    vault_name = sqlobject.StringCol(length=20, default=None)
    action = sqlobject.StringCol(length=20, default="")
    creation_date = sqlobject.DateCol(default=None)
    has_completed = sqlobject.BoolCol(default=False)
    completion_date = sqlobject.DateCol(default=None)
    status_code = sqlobject.StringCol(length=10, default="")
    response_text = sqlobject.StringCol()


def list_vaults(max_vaults=10, iter_marker=None):
    """List Amazon S3 Glacier vaults owned by the AWS account

    :param max_vaults: Maximum number of vaults to retrieve
    :param iter_marker: Marker used to identify start of next batch of vaults
    to retrieve
    :return: List of dictionaries containing vault information
    :return: String marking the start of next batch of vaults to retrieve.
    Pass this string as the iter_marker argument in the next invocation of
    list_vaults().
    """

    # Retrieve vaults
    glacier = boto3.client('glacier')
    if iter_marker is None:
        vaults = glacier.list_vaults(limit=str(max_vaults))
    else:
        vaults = glacier.list_vaults(limit=str(max_vaults), marker=iter_marker)
    marker = vaults.get('Marker')       # None if no more vaults to retrieve
    return vaults['VaultList'], marker


def retrieve_inventory(vault_name):
    """Initiate an Amazon Glacier inventory-retrieval job

    To check the status of the job, call Glacier.Client.describe_job()
    To retrieve the output of the job, call Glacier.Client.get_job_output()

    :param vault_name: string
    :return: Dictionary of information related to the initiated job. If error,
    returns None.
    """

    # Construct job parameters
    job_parms = {'Type': 'inventory-retrieval'}

    # Initiate the job
    glacier = boto3.client('glacier')
    try:
        response = glacier.initiate_job(vaultName=vault_name,
                                        jobParameters=job_parms)
    except ClientError as e:
        logging.error(e)
        return None
    return response


def describe_job(vault_name, job_id):
    """Retrieve the status of an Amazon S3 Glacier job, such as an inventory-retrieval job

    To retrieve the output of the finished job, call Glacier.Client.get_job_output()

    :param vault_name: string
    :param job_id: string. The job ID was returned by Glacier.Client.initiate_job().
    :return: Dictionary of information related to the job. If error, return None
.
    """

    # Retrieve the status of the job
    glacier = boto3.client('glacier')
    try:
        response = glacier.describe_job(vaultName=vault_name, jobId=job_id)
    except ClientError as e:
        logging.error(e)
        return None
    return response


def retrieve_inventory_results(vault_name, job_id):
    """Retrieve the results of an Amazon Glacier inventory-retrieval job

    :param vault_name: string
    :param job_id: string. The job ID was returned by Glacier.Client.initiate_job()
    :return: Dictionary containing the results of the inventory-retrieval job.
    If error, return None.
    """

    # Retrieve the job results
    glacier = boto3.client('glacier')
    try:
        response = glacier.get_job_output(vaultName=vault_name, jobId=job_id)
    except ClientError as e:
        logging.error(e)
        return None

    # Read the streaming results into a dictionary
    return json.loads(response['body'].read())


def delete_archive(vault_name, archive_id):
    """Delete an archive from an Amazon S3 Glacier vault

    :param vault_name: string
    :param archive_id: string
    :return: True if archive was deleted, otherwise False
    """

    # Delete the archive
    glacier = boto3.client('glacier')
    try:
        glacier.delete_archive(vaultName=vault_name, archiveId=archive_id)
    except ClientError as e:
        logging.error(e)
        return False
    return True


def connect_db(db_path):
    db_filename = os.path.abspath(db_path)
    connection_string = 'sqlite:' + db_filename
    connection = sqlobject.connectionForURI(connection_string)
    sqlobject.sqlhub.processConnection = connection


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('action', metavar='ACTION', type=str,
                        help='Specify the action to perform: {}'.format(', '.join(VALID_ACTIONS)))
    parser.add_argument('vault', metavar='VAULT_NAME', type=str, nargs='?', default=None,
                        help='The name of the AWS Glacier Vault')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Display all log messages')
    parser.add_argument('-f', '--filename', metavar='INPUT_FILE', type=str,
                        help='The filename with the log of archive keys')
    parser.add_argument('-j', '--job', metavar='JOB_ID', type=str,
                        help='Job ID to retrieve the inventory results')
    args = parser.parse_args()
    vault_name = args.vault
    archive_ids = []

    connect_db(JOB_STATUS_DB)

    with rich.console.Console() as console:
        if args.debug:
            log_level = logging.DEBUG
        else:
            log_level = logging.INFO
        # Set up logging
        logging.basicConfig(level=log_level,
                            format='%(levelname)s: %(asctime)s: %(message)s')

        if args.action == 'list':
            # List the vaults
            vaults, marker = list_vaults()
            console.print('#     Size         Vault Name')
            console.print('------------------------------')
            while True:
                # Print info about retrieved vaults
                for vault in vaults:
                    console.print(f'{vault["NumberOfArchives"]:3d}  {vault["SizeInBytes"]:12d}  {vault["VaultName"]}')

                # If no more vaults exist, exit loop, otherwise retrieve the next batch
                if marker is None:
                    break
                vaults, marker = list_vaults(iter_marker=marker)
        elif args.action == 'start_inventory':
            if args.vault is not None:
                # Initiate an inventory retrieval job
                response = retrieve_inventory(vault_name)
                if response is not None:
                    console.print(f'Initiated inventory-retrieval job for {vault_name}')
                    console.print(f'Retrieval Job ID: {response["jobId"]}')
                    Job(job_id=response['jobId'],
                        vault_name=vault_name,
                        response_text=json.dumps(response))
            else:
                console.print("Vault Name required for inventory results", style="yellow")
        elif args.action == 'status':
            for job in Job.select():
                if not job.has_completed:
                    response = describe_job(job.vault_name, job.job_id)
                    if response is not None:
                        job.status_code = response['StatusCode']
                        job.action = response['Action']
                        job.creation_date = dateutil.parser.parse(response['CreationDate'])
                        job.has_completed = response['Completed']
                        job.status_code = response['StatusCode']
                        if 'CompletionDate' in response:
                            job.completion_date = dateutil.parser.parse(response['CompletionDate'])
                        job.response_text = json.dumps(response)
                console.print(f"{job.job_id[:10]}...:  {job.action}  {job.status_code}")
        elif args.action == 'get_inventory':
            expiry = datetime.date.today() - datetime.timedelta(days=1)
            for job in Job.select(Job.q.has_completed == True):
                if job.completion_date > expiry:
                    # Retrieve the job results
                    inventory = retrieve_inventory_results(job.vault_name, job.job_id)
                    if inventory is not None:
                        job.response_text = json.dumps(inventory)
                        # Output some of the inventory information
                        console.print(f'Vault ARN: {inventory["VaultARN"]}')
                        for archive in inventory['ArchiveList']:
                            console.print(f'  Size: {archive["Size"]:6d},  Archive ID: {archive["ArchiveId"]},  Description: {archive["ArchiveDescription"]}')
        elif args.action == 'delete':
            with open('archive.txt') as fd:
                for line in fd:
                    try:
                        key = line[line.index('Archive ID:') + 12:].strip()
                        archive_ids.append(key)
                    except ValueError:
                        pass

            # Delete the archive
            for archive_id in archive_ids:
                success = delete_archive(vault_name, archive_id)
                if success:
                    console.print(f'Deleted archive {archive_id} from {vault_name}')
        elif args.action == 'init':
            Job.createTable(ifNotExists=True)
        elif args.action == 'history':
            for job in Job.select(Job.q.has_completed == True):
                inventory = json.loads(job.response_text)
                console.print(f"Vault ARN: {inventory['VaultARN']}")
                for archive in inventory['ArchiveList']:
                    console.print(f'{archive["ArchiveId"]}; {archive["Size"]}; {archive["ArchiveDescription"]}')
        else:
            console.print(f'ERROR: Action [bold]{args.action}[/bold] is not recognized.', style='red')
            console.print('Valid actions are: [cyan]{}[cyan]'.format(' '.join(VALID_ACTIONS)))


if __name__ == '__main__':
    main()
