#include <string.h>
#include <stdio.h>

#include "transapi_internal.h"
#include "xmldiff.h"
#include "../netconf_internal.h"

int transapi_xml_apply_callbacks_recursive(struct xmldiff_tree* tree, struct transapi_xml_data_callbacks* calls) {
	struct xmldiff_tree* child;
	int min_prio = 0, ret;

	child = tree->children;
	while (child != NULL) {
		if (min_prio == 0 && !child->applied && child->priority > 0) {
			/* Set minimal priority with a sensible value (first child's priority) */
			min_prio = child->priority;
			child = child->next;
			continue;
		}

		if (!child->applied && child->priority > 0 && child->priority < min_prio) {
			min_prio = child->priority;
		}
		child = child->next;
	}

	if (min_prio > 0) {
		child = tree->children;
		while (child != NULL) {
			if (!child->apllied && child->priority == min_prio) {
				/* Process this child recursively */
				if (transapi_xml_apply_callbacks_recursive(child, calls) != EXIT_SUCCESS) {
					return EXIT_FAILURE;
				}
				break;
			}
			child = child->next;
		}
	}

	/* Finally call our callback */
	DBG("Transapi calling callback %s with op %d.\n", tree->path, tree->op);
	ret = calls->callbacks[tree->priority-1].func(tree->op, tree->node, &calls->data);
	if (ret != EXIT_SUCCESS) {
		ERROR("Callback for path %s failed (%d)\n.", tree->path, ret);
	}

	return ret;
}

/* will be called by library after change in running datastore */
int transapi_xml_running_changed (struct transapi_xml_data_callbacks * c, const char * ns_mapping[], xmlDocPtr old_doc, xmlDocPtr new_doc, struct model_tree * model)
{
	struct xmldiff_tree* diff = NULL;
	
	if (xmldiff_diff(&diff, old_doc, new_doc, model, ns_mapping) == XMLDIFF_ERR) { /* failed to create diff list */
		ERROR("Failed to create the tree of differences.\n");
		xmldiff_free(diff);
		return EXIT_FAILURE;
	} else if (diff != NULL) {
		if (xmldiff_set_priorities(diff, c) != EXIT_SUCCESS) {
			VERB("There was not found a single callback for the configuration change.\n");
		} else {
			if (transapi_xml_apply_callbacks_recursive(diff, c) != EXIT_SUCCESS) {
				xmldiff_free(diff);
				return EXIT_FAILURE;
			}
		}
	} else {
		VERB("Nothing changed.\n");
	}

	xmldiff_free (diff);
	return EXIT_SUCCESS;
}

/* will be called by library after change in running datastore */
int transapi_running_changed (struct transapi_data_callbacks * c, const char * ns_mapping[], xmlDocPtr old_doc, xmlDocPtr new_doc, struct model_tree * model)
{
	struct xmldiff_tree* diff = NULL;
	int i,j, ret;
	char * last_slash = NULL, * parent_path, *tmp_path = NULL;
	xmlBufferPtr buf;
	char * node;

	if (xmldiff_diff (&diff, old_doc, new_doc, model, ns_mapping) == XMLDIFF_ERR) { /* failed to create diff list */
		ERROR("Failed to create the tree of differences.\n");
		xmldiff_free (diff);
		return EXIT_FAILURE;
	} else if (diff != NULL) {
		//~ buf = xmlBufferCreate();
		//~ for (i=0; i<diff->diff_count; i++) { /* for each diff*/
			//~ DBG("(%d) %s\n", diff->diff_list[i].op, diff->diff_list[i].path);
			//~ for (j=0; j<c->callbacks_count; j++) { /* find callback function */
				//~ if (strcmp(diff->diff_list[i].path, c->callbacks[j].path) == 0) { /* exact match */
					//~ /* call callback function */
					//~ /* if node was removed, it was copied from old XML doc, else from new XML doc */
					//~ xmlNodeDump(buf,diff->diff_list[i].op == XMLDIFF_REM ? old_doc : new_doc, diff->diff_list[i].node, 1, 0);
					//~ node = (char*)xmlBufferContent(buf);
					//~ if ((ret = c->callbacks[j].func(diff->diff_list[i].op, node, &c->data)) != EXIT_SUCCESS) {
						//~ xmldiff_free (diff);
						//~ return EXIT_FAILURE;
					//~ }
					//~ xmlBufferEmpty(buf);
					//~ break;
				//~ }
			//~ }
			//~ if (j == c->callbacks_count) { /* no callback function for given path found */
				//~ VERB("Path %s(%d/%d) has no callback\n", diff->diff_list[i].path, i, diff->diff_count);
			//~ }
		//~ }
		//~ xmlBufferFree(buf);
	} else {
		VERB("Nothing changed.\n");
	}

	xmldiff_free (diff);
	return EXIT_SUCCESS;
}
