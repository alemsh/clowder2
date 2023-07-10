/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */

import type { EventListenerJobDB } from './EventListenerJobDB';
import type { ExtractorInfo } from './ExtractorInfo';
import type { MongoDBRef } from './MongoDBRef';

/**
 * Document Mapping class.
 *
 * Fields:
 *
 * - `id` - MongoDB document ObjectID "_id" field.
 * Mapped to the PydanticObjectId class
 *
 * Inherited from:
 *
 * - Pydantic BaseModel
 * - [UpdateMethods](https://roman-right.github.io/beanie/api/interfaces/#aggregatemethods)
 */
export type VisualizationConfigOut = {
    resource: MongoDBRef;
    extractor_info?: ExtractorInfo;
    job?: EventListenerJobDB;
    client?: string;
    vis_config_data?: any;
    visualization: string;
    visualization_component_id: string;
    id?: string;
}
