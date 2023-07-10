/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */

import type { EventListenerJobDB } from './EventListenerJobDB';
import type { ExtractorInfo } from './ExtractorInfo';
import type { MongoDBRef } from './MongoDBRef';

export type VisualizationConfigIn = {
    resource: MongoDBRef;
    extractor_info?: ExtractorInfo;
    job?: EventListenerJobDB;
    client?: string;
    vis_config_data?: any;
    visualization: string;
    visualization_component_id: string;
}
