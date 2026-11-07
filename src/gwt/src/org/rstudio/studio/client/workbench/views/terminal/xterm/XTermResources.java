/*
 * XTermResources.java
 *
 * Copyright (C) 2022 by Posit Software, PBC
 *
 * Unless you have received this program directly from Posit Software pursuant
 * to the terms of a commercial license agreement with Posit Software, then
 * this program is licensed to you under the terms of version 3 of the
 * GNU Affero General Public License. This program is distributed WITHOUT
 * ANY EXPRESS OR IMPLIED WARRANTY, INCLUDING THOSE OF NON-INFRINGEMENT,
 * MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE. Please refer to the
 * AGPL (http://www.gnu.org/licenses/agpl-3.0.txt) for more details.
 *
 */
package org.rstudio.studio.client.workbench.views.terminal.xterm;

import com.google.gwt.core.client.GWT;
import com.google.gwt.resources.client.ClientBundle;
import org.rstudio.core.client.resources.StaticDataResource;

public interface XTermResources extends ClientBundle
{
   XTermResources INSTANCE = GWT.create(XTermResources.class);

   // ghostty-web: libghostty-vt compiled to WebAssembly (embedded in the
   // script), with an xterm.js-compatible API; see tools/build-ghostty
   @Source("ghostty-web.js")
   StaticDataResource ghosttyjs();

   @Source("ghostty-theme.js")
   StaticDataResource themejs();

   @Source("ghostty-a11y.js")
   StaticDataResource accessibilityjs();

   @Source("file-links.js")
   StaticDataResource filelinksjs();
}
