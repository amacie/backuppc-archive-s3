#!/usr/bin/env python3
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
import logging
import boto3
from botocore.exceptions import ClientError


def delete_archive(vault_name, archive_id):
    """Delete an archive from an Amazon S3 Glacier vault

    :param vault_name: string
    :param archive_id: string
    :return: True if archive was deleted, otherwise False
    """

    # Delete the archive
    glacier = boto3.client('glacier')
    try:
        response = glacier.delete_archive(vaultName=vault_name,
                                          archiveId=archive_id)
    except ClientError as e:
        logging.error(e)
        return False
    return True


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('vault', metavar='VAULT_NAME', type=str,
                        help='The name of the AWS Glacier Vault')
    parser.add_argument('filename', metavar='INPUT_FILE', type=str,
                        help='The filename with the log of archive keys')
    args = parser.parse_args()
    vault_name = args.vault
    archive_ids = []

    # Set up logging
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)s: %(asctime)s: %(message)s')

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
            logging.info(f'Deleted archive {archive_id} from {vault_name}')


if __name__ == '__main__':
    main()
