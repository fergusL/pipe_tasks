#!/usr/bin/env python
#
# LSST Data Management System
# Copyright 2014-2015 LSST/AURA
#
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
# GNU General Public License for more details.
#
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <http://www.lsstcorp.org/LegalNotices/>.
#
import numpy
from lsst.pex.config import Config, Field, DictField
from lsst.pipe.base import Task
import lsst.afw.geom as afwGeom
import lsst.afw.table as afwTable

__all__ = ('PropagateVisitFlagsConfig', 'PropagateVisitFlagsTask')


class PropagateVisitFlagsConfig(Config):
    """Configuration for propagating flags to coadd"""
    flags = DictField(keytype=str, itemtype=float,
                      default={"calib_psf_candidate": 0.2, "calib_psf_used": 0.2, "calib_psf_reserved": 0.2,
                               "calib_astrometry_used": 0.2, "calib_photometry_used": 0.2,
                               "calib_photometry_reserved": 0.2, },
                      doc=("Source catalog flags to propagate, with the threshold of relative occurrence "
                           "(valid range: [0-1], default is 0.2).  Coadd object will have flag set if the "
                           "fraction of input visits in which it is flagged is greater than the threshold."))
    matchRadius = Field(dtype=float, default=0.2, doc="Source matching radius (arcsec)")


## \addtogroup LSST_task_documentation
## \{
## \page PropagateVisitFlagsTask
## \ref PropagateVisitFlagsTask_ "PropagateVisitFlagsTask"
## \copybrief PropagateVisitFlagsTask
## \}

class PropagateVisitFlagsTask(Task):
    """Task to propagate flags from single-frame measurements to coadd measurements

Notes
-----
We want to be able to set a flag for sources on the coadds using flags
that were determined from the individual visits.  A common example is sources
that were used for PSF determination, since we do not do any PSF determination
on the coadd but use the individual visits.  This requires matching the coadd
source catalog to each of the catalogs from the inputs (see
PropagateVisitFlagsConfig.matchRadius), and thresholding on the number of
times a source is flagged on the input catalog.

An important consideration in this is that the flagging of sources in the
individual visits can be somewhat stochastic, e.g., the same stars may not
always be used for PSF determination because the field of view moves slightly
between visits, or the seeing changed.  We there threshold on the relative
occurrence of the flag in the visits (see PropagateVisitFlagsConfig.flags).
Flagging a source that is always flagged in inputs corresponds to a threshold
of 1, while flagging a source that is flagged in any of the input corresponds
to a threshold of 0.  But neither of these extrema are really useful in
practise.

Setting the threshold too high means that sources that are not consistently
flagged (e.g., due to chip gaps) will not have the flag propagated.  Setting
that threshold too low means that random sources which are falsely flagged in
the inputs will start to dominate.  If in doubt, we suggest making this
threshold relatively low, but not zero (e.g., 0.1 to 0.2 or so).  The more
confidence in the quality of the flagging, the lower the threshold can be.

The relative occurrence accounts for the edge of the field-of-view of the
camera, but does not include chip gaps, bad or saturated pixels, etc.

Initialization

Beyond the usual Task initialization, PropagateVisitFlagsTask also requires
a schema for the catalog that is being constructed.

The 'run' method (described below) is the entry-point for operations.  The
'getCcdInputs' staticmethod is provided as a convenience for retrieving the
'ccdInputs' (CCD inputs table) from an Exposure.

.. code-block :: none

    # Requires:
    # * butler: data butler, for retrieving the CCD catalogs
    # * coaddCatalog: catalog of source measurements on the coadd (lsst.afw.table.SourceCatalog)
    # * coaddExposure: coadd (lsst.afw.image.Exposure)
    from lsst.pipe.tasks.propagateVisitFlags import PropagateVisitFlagsTask, PropagateVisitFlagsConfig
    config = PropagateVisitFlagsConfig()
    config.flags["calib_psf_used"] = 0.3 # Relative threshold for this flag
    config.matchRadius = 0.5 # Matching radius in arcsec
    task = PropagateVisitFlagsTask(coaddCatalog.schema, config=config)
    ccdInputs = task.getCcdInputs(coaddExposure)
    task.run(butler, coaddCatalog, ccdInputs, coaddExposure.getWcs())

"""
    ConfigClass = PropagateVisitFlagsConfig

    def __init__(self, schema, **kwargs):
        Task.__init__(self, **kwargs)
        self.schema = schema
        self._keys = dict((f, self.schema.addField(f, type="Flag", doc="Propagated from visits")) for
                          f in self.config.flags)

    @staticmethod
    def getCcdInputs(coaddExposure):
        """!Convenience method to retrieve the CCD inputs table from a coadd exposure"""
        return coaddExposure.getInfo().getCoaddInputs().ccds

    def run(self, butler, coaddSources, ccdInputs, coaddWcs):
        """Propagate flags from individual visit measurements to coadd

        This requires matching the coadd source catalog to each of the catalogs
        from the inputs, and thresholding on the number of times a source is
        flagged on the input catalog.  The threshold is made on the relative
        occurrence of the flag in each source.  Flagging a source that is always
        flagged in inputs corresponds to a threshold of 1, while flagging a
        source that is flagged in any of the input corresponds to a threshold of
        0.  But neither of these extrema are really useful in practise.

        Setting the threshold too high means that sources that are not consistently
        flagged (e.g., due to chip gaps) will not have the flag propagated.  Setting
        that threshold too low means that random sources which are falsely flagged in
        the inputs will start to dominate.  If in doubt, we suggest making this threshold
        relatively low, but not zero (e.g., 0.1 to 0.2 or so).  The more confidence in
        the quality of the flagging, the lower the threshold can be.

        The relative occurrence accounts for the edge of the field-of-view of
        the camera, but does not include chip gaps, bad or saturated pixels, etc.

        @param[in] butler  Data butler, for retrieving the input source catalogs
        @param[in,out] coaddSources  Source catalog from the coadd
        @param[in] ccdInputs  Table of CCDs that contribute to the coadd
        @param[in] coaddWcs  Wcs for coadd
        """
        if len(self.config.flags) == 0:
            return

        flags = self._keys.keys()
        visitKey = ccdInputs.schema.find("visit").key
        ccdKey = ccdInputs.schema.find("ccd").key
        radius = self.config.matchRadius*afwGeom.arcseconds

        self.log.info("Propagating flags %s from inputs" % (flags,))

        counts = dict((f, numpy.zeros(len(coaddSources), dtype=int)) for f in flags)
        indices = numpy.array([s.getId() for s in coaddSources])  # Allowing for non-contiguous data

        # Accumulate counts of flags being set
        for ccdRecord in ccdInputs:
            v = ccdRecord.get(visitKey)
            c = ccdRecord.get(ccdKey)
            ccdSources = butler.get("src", visit=int(v), ccd=int(c), immediate=True)
            for sourceRecord in ccdSources:
                sourceRecord.updateCoord(ccdRecord.getWcs())
            for flag in flags:
                # We assume that the flags will be relatively rare, so it is more efficient to match
                # against a subset of the input catalog for each flag than it is to match once against
                # the entire catalog.  It would be best to have built a kd-tree on coaddSources and
                # keep reusing that for the matching, but we don't have a suitable implementation.
                mc = afwTable.MatchControl()
                mc.findOnlyClosest = False
                matches = afwTable.matchRaDec(coaddSources, ccdSources[ccdSources.get(flag)], radius, mc)
                for m in matches:
                    index = (numpy.where(indices == m.first.getId()))[0][0]
                    counts[flag][index] += 1

        # Apply threshold
        for f in flags:
            key = self._keys[f]
            for s, num in zip(coaddSources, counts[f]):
                numOverlaps = len(ccdInputs.subsetContaining(s.getCentroid(), coaddWcs, True))
                s.setFlag(key, bool(num > numOverlaps*self.config.flags[f]))
            self.log.info("Propagated %d sources with flag %s" % (sum(s.get(key) for s in coaddSources), f))
