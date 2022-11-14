/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */

import type { EventListenerIn } from './EventListenerIn';
import type { LegacyEventListenerIn } from './LegacyEventListenerIn';

export type MetadataIn = {
    id?: string;
    context?: any;
    context_url?: string;
    definition?: string;
    contents: any;
    file_version?: number;
    listener?: EventListenerIn;
    extractor?: LegacyEventListenerIn;
}
